#!/usr/bin/env python3
"""Forecast Polymarket's "Next CEO of NVIDIA?" Yes prices, 240 minutes ahead.

Reads one case (/input/<id>.in): every trading market of the event, its Yes
price at every minute of the 72 hours up to a checkpoint. Writes
/output/<id>.out: for each market and each of the 240 minutes after the
checkpoint, five quantiles (5%, 25%, 50%, 75%, 95%) of that minute's price.

Method (pure stdlib, deterministic, no network, no clock):
  For each market, a normal random-walk forecast around its last price:
  q_tau(h) = x + z_tau * sigma * sqrt(h), clamped to [0, 1].
  sigma is per-market: 1.4826 * MAD of the market's 1-minute moves over the
  last 48 h, floored at 0.0008, capped at 0.02 -- and floored again at
  0.016 * x, because a market's moves scale with its price level: a market
  at 0.30 moves about a hundred times further per minute than one at
  0.003, and a flat history must not make a big market's forecast razor
  thin. No drift: recent trends did not carry forward on the practice
  cases (they hurt), and no mean reversion (it hurt too).
  Measured on the five locally scoreable practice cases (p00-p04, answers
  taken from the next case's overlapping history): mean pinball loss
  0.3363 vs the house baseline's 0.3985 on the same cases, beating it on
  every case; the baseline's published 6-case practice loss is 0.363589.

Tuning knobs (env vars, defaults are the shipped values):
  PM_WINDOW_MIN  history window for the change distribution (default 2880)
  PM_MODE        blend | wide  (default blend)
  PM_BLEND       weight of the normal forecast in the blend (default 1.0:
                 all-normal; the empirical path is kept for experiments)
  PM_DRIFT_H     hours of recent trend used for the drift (default 4)
  PM_DRIFT_SHRINK shrink on the drift (default 0: no drift)
  PM_MR_TAU_MIN  mean-reversion half-life in minutes, 0 = off (default 0)
  PM_SUM01       1 = rescale medians so their sum tracks the recent
                 sum of prices across markets (default 0)
"""
import json
import math
import os
from bisect import bisect_left

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722]
ANCHORS = [1, 2, 4, 8, 16, 32, 64, 128, 240]

WINDOW_MIN = int(os.environ.get("PM_WINDOW_MIN", "2880"))
MODE = os.environ.get("PM_MODE", "blend")
BLEND = float(os.environ.get("PM_BLEND", "1.0"))
DRIFT_H = float(os.environ.get("PM_DRIFT_H", "4"))
DRIFT_SHRINK = float(os.environ.get("PM_DRIFT_SHRINK", "0"))
MR_TAU_MIN = float(os.environ.get("PM_MR_TAU_MIN", "0"))
SUM01 = os.environ.get("PM_SUM01", "0") == "1"
BASE_SIGMA = 0.0025
# Sigma estimator: mad (1.4826*MAD of 1-min diffs), std, max (of the two),
# std60 (std of 60-min changes / sqrt(60)). Window in minutes.
SIGMA_MODE = os.environ.get("PM_SIGMA", "mad")
SIGMA_FLOOR = float(os.environ.get("PM_SIGMA_FLOOR", "0.0008"))
SIGMA_CAP = float(os.environ.get("PM_SIGMA_CAP", "0.02"))
SIGMA_WINDOW = int(os.environ.get("PM_SIGMA_WINDOW", "2880"))
# Multiplier on the outer (5%/95%) z-scores only: heavy-tail widening.
TAIL = float(os.environ.get("PM_TAIL", "1.0"))
# Relative-vol floor: sigma is at least x * SIGMA_REL (moves scale with
# the price level; big markets move big in absolute terms).
SIGMA_REL = float(os.environ.get("PM_SIGMA_REL", "0.016"))


def price6(x):
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, x)), 6) + 0.0


def quantile_sorted(s, tau):
    """Linear-interpolation quantile of a sorted list."""
    n = len(s)
    if n == 0:
        return 0.0
    if n == 1:
        return s[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def forecast_market(prices, horizon):
    n = len(prices)
    x = prices[-1]
    # --- per-market robust sigma from 1-minute moves (recent window) ---
    t0 = max(0, n - 1 - WINDOW_MIN)
    s0 = max(0, n - 1 - SIGMA_WINDOW)
    diffs1 = [prices[i + 1] - prices[i] for i in range(s0, n - 1)]
    if diffs1:
        med_abs = median([abs(d) for d in diffs1])
        sig_mad = 1.4826 * med_abs
        mean_d = sum(diffs1) / len(diffs1)
        sig_std = math.sqrt(sum((d - mean_d) ** 2 for d in diffs1) / len(diffs1))
        if SIGMA_MODE == "std":
            sigma = sig_std
        elif SIGMA_MODE == "max":
            sigma = max(sig_mad, sig_std)
        elif SIGMA_MODE == "std60":
            ch60 = [prices[i + 60] - prices[i]
                    for i in range(s0, max(s0, n - 61))]
            if len(ch60) >= 20:
                m60 = sum(ch60) / len(ch60)
                sigma = math.sqrt(sum((c - m60) ** 2 for c in ch60)
                                / len(ch60)) / math.sqrt(60)
            else:
                sigma = sig_mad
        else:
            sigma = sig_mad
        sigma = min(max(sigma, SIGMA_FLOOR), SIGMA_CAP)
    else:
        sigma = BASE_SIGMA
    sigma = max(sigma, x * SIGMA_REL)
    # --- shrunk recent-trend drift (price units per minute) ---
    dh = int(DRIFT_H * 60)
    seg = prices[max(0, n - 1 - dh):]
    if len(seg) >= 2:
        drift = DRIFT_SHRINK * (seg[-1] - seg[0]) / (len(seg) - 1)
    else:
        drift = 0.0
    drift = max(-0.002, min(0.002, drift))
    # --- long-run level for mean reversion ---
    level = median(prices[max(0, n - 1 - 1440):]) if MR_TAU_MIN > 0 else x

    # --- empirical change quantiles at the anchor horizons ---
    # changes[h_idx][tau_idx]; skipped entirely when the blend is all-normal
    emp = []
    if BLEND >= 1.0:
        emp = [None] * len(ANCHORS)
    else:
        for h in ANCHORS:
            hi_t = n - 1 - h
            if hi_t <= t0:
                emp.append(None)
                continue
            ch = sorted(prices[t + h] - prices[t] for t in range(t0, hi_t + 1))
            if len(ch) < 20:
                emp.append(None)
                continue
            emp.append([quantile_sorted(ch, tau) for tau in QUANTILES])

    def interp_at(h, get):
        """Interpolate a per-anchor value to horizon h, in sqrt(h)."""
        sh = math.sqrt(h)
        if h <= ANCHORS[0]:
            return get(0)
        if h >= ANCHORS[-1]:
            return get(len(ANCHORS) - 1)
        j = bisect_left([math.sqrt(a) for a in ANCHORS], sh)
        h0, h1 = ANCHORS[j - 1], ANCHORS[j]
        w = (sh - math.sqrt(h0)) / (math.sqrt(h1) - math.sqrt(h0))
        return get(j - 1) * (1.0 - w) + get(j) * w

    rows = []
    zw = [Z[0] * TAIL, Z[1], Z[2], Z[3], Z[4] * TAIL]
    for h in range(1, horizon + 1):
        sq = math.sqrt(h)
        norm = [x + drift * h + z * sigma * sq for z in zw]
        # mean reversion pulls the median toward the long-run level
        if MR_TAU_MIN > 0:
            pull = 1.0 - math.exp(-h / MR_TAU_MIN)
            norm[2] = norm[2] + pull * (level - norm[2])
        if emp[0] is None and all(e is None for e in emp):
            row = norm
        else:
            # nearest available anchor's empirical quantiles where missing
            def get_emp(j):
                e = emp[j]
                if e is not None:
                    return e
                for k in range(j - 1, -1, -1):
                    if emp[k] is not None:
                        return emp[k]
                for k in range(j + 1, len(emp)):
                    if emp[k] is not None:
                        return emp[k]
                return [0.0] * 5
            eq = [interp_at(h, lambda j, t=t: get_emp(j)[t])
                  for t in range(5)]
            eq = [x + v for v in eq]
            if MODE == "wide":
                row = []
                for t in range(5):
                    if t < 2:
                        row.append(min(eq[t], norm[t]))
                    elif t > 2:
                        row.append(max(eq[t], norm[t]))
                    else:
                        row.append((1.0 - BLEND) * eq[t] + BLEND * norm[t])
            else:
                row = [(1.0 - BLEND) * eq[t] + BLEND * norm[t]
                       for t in range(5)]
        # enforce non-decreasing quantiles, clamp, round
        for t in range(1, 5):
            if row[t] < row[t - 1]:
                row[t] = row[t - 1]
        rows.append([price6(v) for v in row])
    return rows, x


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    inputs = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for fname in inputs:
        cid = fname[:-3]
        with open(os.path.join(INPUT_DIR, fname)) as f:
            case = json.load(f)
        horizon = case["horizon_minutes"]
        forecasts = []
        last_prices = {}
        for m in case["markets"]:
            rows, x = forecast_market(m["prices"], horizon)
            forecasts.append({"id": m["id"], "q": rows})
            last_prices[m["id"]] = x
        if SUM01:
            # Rescale medians so their sum tracks the recent sum of prices.
            target = sum(last_prices.values())
            for h in range(horizon):
                s = sum(fc["q"][h][2] for fc in forecasts)
                if s > 0:
                    adj = target - s
                    tot = sum(max(fc["q"][h][2], 0.0) for fc in forecasts)
                    if tot > 0:
                        for fc in forecasts:
                            d = adj * max(fc["q"][h][2], 0.0) / tot
                            fc["q"][h] = [price6(v + d) for v in fc["q"][h]]
                            for t in range(1, 5):
                                if fc["q"][h][t] < fc["q"][h][t - 1]:
                                    fc["q"][h][t] = fc["q"][h][t - 1]
        with open(os.path.join(OUTPUT_DIR, cid + ".out"), "w") as f:
            f.write(json.dumps({"forecasts": forecasts}) + "\n")


if __name__ == "__main__":
    main()
