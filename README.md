# polymarket-nvidia-ceo-forecast

[![make.fun · polymarket-nvidia-ceo-forecast-01](https://make.fun/badge/polymarket-nvidia-ceo-forecast-01.svg)](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=polymarket-nvidia-ceo-forecast-01)
[![rank](https://make.fun/badge/polymarket-nvidia-ceo-forecast-01/naufalumer/polymarket-nvidia-ceo-forecast/rank.svg)](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=polymarket-nvidia-ceo-forecast-01)
[![reward](https://make.fun/badge/polymarket-nvidia-ceo-forecast-01/naufalumer/polymarket-nvidia-ceo-forecast/reward.svg)](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=polymarket-nvidia-ceo-forecast-01)

Entry for make.fun competition `polymarket-nvidia-ceo-forecast-01`:
forecast Polymarket's "Next CEO of NVIDIA?" Yes prices minute by minute,
4 hours ahead, as five quantiles (5%, 25%, 50%, 75%, 95%) per market per
minute, scored by mean pinball loss.

## Program

`main.py` — pure Python 3.13 standard library, no network, no clock,
deterministic (two runs on the same case are byte-identical). Reads
`$MAKEFUN_INPUT_DIR/<id>.in`, writes `$MAKEFUN_OUTPUT_DIR/<id>.out`.

Model: a normal random walk around each market's last price,
`q_tau(h) = x + z_tau * sigma * sqrt(h)`. Sigma is per-market:
`1.4826 * MAD` of the market's 1-minute moves over the last 48 h, floored
at 0.0008 and capped at 0.02 — and floored again at `0.016 * x`, because a
market's moves scale with its price level: a market at 0.30 moves about a
hundred times further per minute than one at 0.003, and a flat history must
not make a big market's forecast razor thin. No drift and no mean
reversion: on the practice cases both hurt (recent trends did not carry
forward).

## Scores (measured locally on the kit's practice cases)

Practice answers for p00–p04 were taken from the next case's overlapping
history (the kit ships no reference answers; p05 is unscored locally).
Mean pinball loss **0.3363** vs the house baseline's **0.3985** on the same
five cases — beating it on every case (p00 0.480 vs 0.536, p01 0.315 vs
0.380, p02 0.346 vs 0.408, p03 0.322 vs 0.369, p04 0.218 vs 0.299). The
baseline's published 6-case practice loss is 0.363589. Whether it beats
the house AI model forecast on the final is unknowable until grading.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## License

MIT — see LICENSE.
