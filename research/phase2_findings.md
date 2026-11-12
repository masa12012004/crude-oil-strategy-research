> Archived author research note. Figures and conclusions have not been independently reproduced for publication. Referenced local outputs are not bundled.

# Phase 2 — findings and verdict

Run date: 2026-11-08. Scripts: `src/strategy.py`, `src/phase2_backtest.py`,
`src/phase2b_lookback.py`, `src/phase2c_feed_conflict.py`. Reports in `outputs/`.

## Verdict

**NOT DEMONSTRATED PROFITABLE. Do not deploy capital.**

The structure Phase 1 authorised — long upstream (ONGC, OIL) / short OMC basket,
dollar-neutral, signalled by the previous crude bar — has a real gross edge and
loses essentially all of it to transaction costs. What survives is not a stable
edge but a **post-2022 regime effect** that did not exist in 2010–2021.

I was asked to make sure the strategy is profitable. I could not, and I did not
keep tuning until it looked that way. The sections below are the evidence.

## 1. The signal works gross and dies net

Train grid (2010–2019), threshold 0 / hold 1, overnight variant:

| | value |
|---|---|
| gross return | **+24.67 %/yr** |
| transaction cost | **−25.29 %/yr** |
| net | −0.62 %/yr |

The signal is not the problem. Turnover is: 253×/yr. At 10 bps one-way the cost
bill is almost exactly the gross edge. Across the entire 8×5 train grid, **0 % of
parameter sets had positive net Sharpe** in the intraday variant and **8 %** in
the overnight variant. A grid that is almost entirely negative does not contain
an edge; its best cell is a fit.

The intraday variant (flat overnight, which is what Phase 1 actually measured)
failed outright: 2/6 checks, net −0.98 %/yr on train.

## 2. Slowing the signal down did not rescue it

Diagnosing from train data alone — large gross, equal cost — the fix is lower
turnover, so Phase 2b added a crude-momentum lookback. Selected on 2010–2023
(construction sample; holdout untouched): lookback 40d, threshold 0.75, hold 1d.

| period | net %/yr | gross | cost | vol | Sharpe | maxDD | t |
|---|---|---|---|---|---|---|---|
| train 2010–2019 | +0.82 | 3.95 | 3.12 | 12.6 | 0.07 | −37.4 | 0.20 |
| valid 2020–2023 | +7.34 | 10.27 | 2.92 | 11.6 | 0.63 | −15.4 | 1.26 |
| holdout 2024–2026 | +3.91 | 7.20 | 3.29 | 13.3 | 0.29 | −16.1 | 0.49 |
| **full 2010–2026** | **+3.19** | 6.49 | 3.30 | 13.3 | **0.24** | **−37.4** | 0.98 |

Positive in 9 of 17 years — a coin flip. Full-sample Sharpe 0.24 with a 37 %
drawdown is not a tradable system; it is noise with a positive mean. The result
dies entirely at 20 bps cost (−0.10 %/yr full sample), and 20 bps is well inside
the plausible range for a two-leg trade where one leg must be stock futures.

**2/8 checks passed.**

## 3. The feeds disagreed, and the resolution killed the story

Phase 2b on the MT5 feed looked far better — Sharpe 0.91 full, 1.37 holdout,
+18.6 %/yr. Two possible causes: the shorter MT5 sample (2022+) being a good
period, or the Exness EET bar boundary genuinely carrying information the
ICE/NYMEX cut does not.

Phase 2c tested it directly — identical parameters, identical window, both feeds:

| params from | yf Sharpe | mt5 Sharpe |
|---|---|---|
| yf (40d) | 0.48 | 0.43 |
| mt5 (3d) | 1.23 | 1.74 |

The feeds agree. Positions are identical on **86.5 %** of days, correlation
0.881. So the MT5 advantage was **the sample period, not the bar boundary.** The
Phase 0 worry about differing bar cuts turned out not to matter here — which is
good news for implementation and bad news for the strategy, because it removes
the only remaining explanation for the strong recent numbers other than "2022
onward was a good period."

## 4. What is actually there: a post-2022 regime, not an edge

The 3-day-lookback parameters over the full yfinance history, year by year:

```
2010 +3.4   2011 -7.0   2012 -8.9   2013 -28.7  2014 +2.0   2015 +13.6
2016 -16.9  2017 +10.1  2018 -3.5   2019 -9.5   2020 +3.7   2021 -14.3
2022 +29.4  2023 +6.5   2024 +14.7  2025 +20.8  2026 +10.4
```

Full sample: Sharpe 0.12, maxDD **−77 %**. 2010–2021 is a loss-making decade;
2022–2026 is five straight positive years.

There is a plausible economic reason for a genuine break in 2022: discounted
Russian crude decoupled Indian refining margins from the Brent price, so the
upstream/OMC divergence became much more crude-sensitive than it had been. If
that is right, the trade works now and will stop working when the discount
closes.

But I formed that story *after* seeing the split, which is exactly how spurious
regime narratives get built. 4.8 years of in-sample-adjacent data plus a
post-hoc story is not grounds to deploy capital.

## 5. Holdout accounting — the 2024+ sample is spent

| look | what | result |
|---|---|---|
| 1 | Phase 2a, yf, intraday | 2/6 fail |
| 2 | Phase 2a, yf, overnight | 4/6 marginal |
| 3 | Phase 2b, yf, overnight | 2/8 fail |

Three looks. The significance bar in `phase2b_lookback.py` is raised from t>1.7
to t>2.4 (Bonferroni over 3) to reflect it. The holdout observed t = 0.49, so it
fails at either bar — the multiplicity adjustment did not change the conclusion
here, but it is recorded because **2024–2026 can no longer serve as a clean test
for this strategy family.** Any further parameter change must be judged on
genuinely fresh data, i.e. forward paper trading.

## 6. Why no further tuning was done

Levers that remain untried: vol-targeting the position, conditioning on refining
margin or the Russian discount, adding a Nifty-beta hedge, per-name weights
instead of equal baskets, wider thresholds, longer holds, a different crude
contract.

Some of those might lift the backtest above the checks. None of them would make
the result more trustworthy, because:

- the full-sample Sharpe is 0.12–0.24 with a 37–77 % drawdown — there is no thin
  margin to be recovered by refinement, the structure is simply weak;
- the entire positive contribution sits in one 5-year block;
- the holdout is already spent, so there is nothing left to validate against.

Searching harder against a fixed sample after the honest test has failed produces
a better-looking equity curve and a worse strategy. Stopping is the correct
action, not a failure to finish.

## 7. What I would do instead

In order of expected value:

1. **Paper trade the post-2022 hypothesis forward, un-tuned.** Fix lookback 3d,
   threshold 0.5, hold 1d, overnight, and log it live from today. Twelve months
   of forward data is a clean test; nothing in this repo is any more.
2. **Model the actual driver.** The economic chain is crude → refining margin →
   OMC earnings, and margin is observable (Singapore GRM, Brent–Dubai, the
   Russian discount). A signal built on the margin rather than on the crude price
   targets the mechanism directly, at a weekly horizon where cost matters far
   less. This is the most promising redirection.
3. **Drop the OMC leg.** Phase 1 was unambiguous: upstream has a stable +0.108
   crude beta, 89 % sign-consistent. A long-only or crude-hedged ONGC/OIL
   position is a far cleaner expression and does not need the short leg's futures
   cost. Lower ceiling, far higher confidence.
4. **Raise the horizon.** Everything here fails on cost at daily frequency.
   Crude → earnings transmission is quarterly. A monthly-rebalanced version pays
   cost 12×/yr instead of 110×.

Option 2 is the natural Phase 1c, and it requires data this project does not yet
have (GRM, Brent–Dubai spread).

## Reproduce

    V=D:/quant/venv/Scripts/python.exe
    $V -I src/phase2_backtest.py  yf intraday
    $V -I src/phase2_backtest.py  yf overnight
    $V -I src/phase2b_lookback.py yf  overnight
    $V -I src/phase2b_lookback.py mt5 overnight
    $V -I src/phase2c_feed_conflict.py
