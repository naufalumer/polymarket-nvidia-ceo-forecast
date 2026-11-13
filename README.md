# polymarket-nvidia-ceo-forecast-01 — Relative-vol random walk

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](main.py)
[![Competition](https://img.shields.io/badge/make.fun-polymarket--nvidia--ceo--forecast--01-green.svg)](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01)

Entry for make.fun's `polymarket-nvidia-ceo-forecast-01`: forecast the Yes
price of every trading market of Polymarket's "Next CEO of NVIDIA?" event
at every minute of the 4 hours after a checkpoint, as five quantiles
(0.05, 0.25, 0.5, 0.75, 0.95) per minute. Scored by mean pinball loss.

## Method

A normal random walk around each market's last price, with a per-market
volatility estimated from its own recent moves:

```
q_tau(h) = clamp(x + z_tau * sigma * sqrt(h), 0, 1)
```

- `x` — the market's price at the checkpoint.
- `z_tau` — the standard normal quantile at level tau.
- `h` — the minute 1..240 after the checkpoint.
- `sigma = 1.4826 * MAD` of the market's 1-minute moves over the last
  48 hours, floored at 0.0008, capped at 0.02, and floored at
  `0.016 * x` — moves scale with the price level, so a market sitting
  at 0.50 moves further per minute than one sitting at 0.02.

No drift, no mean reversion: both were tried on the practice cases and
both made the score worse. The median stays at the last price; only
the spread adapts, per market, from what that market actually did.

`main.py` is pure stdlib Python, deterministic (two runs on the same
case write identical bytes), no network, ~0.1 s per case (limit 8 s).
It reads every `*.in` in `$MAKEFUN_INPUT_DIR` (else `/input`) and
writes `<id>.out` to `$MAKEFUN_OUTPUT_DIR` (else `/output`).

## Practice scores (local scorer, cases p00–p04)

| case | this entry | house baseline |
|------|-----------:|---------------:|
| p00  | 0.480178   | 0.536138       |
| p01  | 0.314952   | 0.380352       |
| p02  | 0.345852   | 0.408408       |
| p03  | 0.315101   | 0.368599       |
| p04  | 0.218425   | 0.298794       |
| **mean** | **0.334902** | **0.398458** |

Mean pinball loss **0.334902** vs the house baseline's **0.398458** —
beating it on every case. Scores re-verified in a fresh rebuild session
on 2026-11-13 (see STATUS.md); the house baseline's published
6-case practice loss is 0.363589.

Rejected variants, re-tested in the same rebuild session (mean loss
over the same 5 cases): mean-move drift 0.675631, mean reversion to
the 48 h mean (k = 0.01/min) 1.229198, std-based sigma 1.116066 — all
worse than 0.334902.

Honest note: beating the house *baseline* on practice says nothing
about beating the house *AI model* forecast on the final — that is
unknowable until grading.

## License

MIT — see [LICENSE](LICENSE).
