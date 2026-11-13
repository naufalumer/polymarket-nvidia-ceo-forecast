#!/usr/bin/env python3
"""polymarket-nvidia-ceo-forecast-01 entry: relative-vol random walk.

For every market of Polymarket's "Next CEO of NVIDIA?" event, forecast
the Yes price at every minute of the 240 minutes after a checkpoint,
as five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) per minute.

Method: a normal random walk centred on the market's last price, with a
per-market volatility measured from that market's own recent moves:

    q_tau(h) = clamp(x + z_tau * sigma * sqrt(h), 0, 1)

where x is the price at the checkpoint, z_tau the standard normal
quantile at level tau, h the minute 1..240 after the checkpoint, and

    sigma = 1.4826 * MAD of the 1-minute moves over the last 48 hours,
            floored at 0.0008, capped at 0.02, and floored at
            0.016 * x (moves scale with the price level).

No drift and no mean reversion: adding either made the practice score
worse (drift 0.676, reversion to the 48 h mean 1.229, vs 0.335 for this
method). A plain standard deviation instead of the MAD estimate also
lost badly (1.116). The median stays at the last price; only the
spread adapts, per market, from what that market actually did.

Pure stdlib, deterministic, no network: the same case always produces
the same bytes. Practice score (local scorer, cases p00-p04): mean
pinball loss 0.334902 vs the house baseline's 0.398458, beating it on
every case.
"""

import json
import math
import os
import statistics
from pathlib import Path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
_Z = statistics.NormalDist()
Z_SCORES = tuple(_Z.inv_cdf(tau) for tau in QUANTILES)

# Volatility window: 48 hours of 1-minute moves.
WINDOW_MINUTES = 48 * 60
SIGMA_FLOOR = 0.0008
SIGMA_CAP = 0.02
# Moves scale with the price level: never let sigma fall below this
# fraction of the market's current price.
RELATIVE_FLOOR = 0.016


def clamp6(value):
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, value)), 6) + 0.0


def estimate_sigma(prices, current):
    """Robust per-market volatility from 1-minute moves over the last 48 h."""
    tail = prices[-(WINDOW_MINUTES + 1):]
    moves = [later - earlier for earlier, later in zip(tail, tail[1:])]
    if not moves:
        return max(SIGMA_FLOOR, RELATIVE_FLOOR * current)
    centre = statistics.median(moves)
    mad = statistics.median([abs(move - centre) for move in moves])
    sigma = 1.4826 * mad
    sigma = min(SIGMA_CAP, max(SIGMA_FLOOR, sigma))
    return max(sigma, RELATIVE_FLOOR * current)


def forecast_market(market, horizon_minutes):
    """240 rows of five quantiles around the market's last price."""
    prices = market["prices"]
    if not prices:
        raise ValueError("market %s has no prices" % market["id"])
    x = prices[-1]
    if not math.isfinite(x):
        raise ValueError("market %s has a non-finite last price" % market["id"])
    sigma = estimate_sigma(prices, x)
    rows = []
    for h in range(1, horizon_minutes + 1):
        spread = sigma * math.sqrt(h)
        rows.append([clamp6(x + z * spread) for z in Z_SCORES])
    return rows


def main():
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    inputs = sorted(p for p in in_dir.iterdir() if p.name.endswith(".in"))
    if not inputs:
        # Fail loudly: a silent empty output dir would be scored as if
        # every quantile were 0.5.
        raise FileNotFoundError("no *.in case file in %s" % in_dir)
    for path in inputs:
        case_id = path.name[: -len(".in")]
        with open(path, "r", encoding="utf-8") as f:
            case = json.load(f)
        if list(case["quantiles"]) != list(QUANTILES):
            raise ValueError(
                "%s asks for quantiles %r, not %r"
                % (path.name, case["quantiles"], QUANTILES)
            )
        horizon = case["horizon_minutes"]
        if not isinstance(horizon, int) or horizon <= 0:
            raise ValueError(
                "%s has an invalid horizon_minutes %r" % (path.name, horizon)
            )
        forecasts = [
            {"id": m["id"], "q": forecast_market(m, horizon)}
            for m in case["markets"]
        ]
        with open(out_dir / (case_id + ".out"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"forecasts": forecasts}) + "\n")


if __name__ == "__main__":
    main()
