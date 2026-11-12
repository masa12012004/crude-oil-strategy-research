> Archived author research note. Figures and conclusions have not been independently reproduced for publication. Referenced local outputs are not bundled.

# Phase 5 — rebuild on Phase 4's execution finding, with a 6-level crude regime

Run date: 2026-11-09. Script: `src/phase5_rebuild.py`.
Output: `outputs/phase5_rebuild_yf.txt`, `outputs/phase5_wf_V*_yf.csv`.

## Verdict first

**The rebuild did not produce a better strategy. It produced a better
explanation of the existing one, and it rejected the regime idea on evidence.**

The recommendation is unchanged from Phase 3: long/flat ONGC + Oil India, timed
by Brent momentum, entered at the open and held to the next open, vol-targeted
to 15%. Roughly **+7.5 %/yr, Sharpe 0.66, maxDD −24.7 %** over a 12-year
walk-forward. Phase 5 adds three things that change how much confidence that
number deserves and what must not be done to it.

## 1. The phantom edge, priced

Phase 4 established that 70–104 % of each stock's response to crude lands in the
overnight gap `close[t-1] → open[t]`, which spans the moment the crude bar
closes (~03:30 IST) and therefore cannot be traded. Phase 5 runs the identical
signal through four execution variants to put a number on what that costs.

| | execution | gross %/yr | cost %/yr | net %/yr | Sharpe | t |
|---|---|---|---|---|---|---|
| V1 | open[t] → open[t+1] (Phase 3's) | +15.09 | 1.97 | **+13.12** | **+0.61** | +2.08 |
| V2 | open[t] → close[t] — intraday only | +0.46 | 3.31 | −2.85 | −0.41 | −1.39 |
| V3 | close[t] → open[t+1] — overnight only | +28.15 | 23.98 | +4.17 | +0.45 | +1.53 |
| V4 | close[t-1] → close[t] — **lookahead control** | +26.47 | 4.73 | +21.74 | +1.97 | +6.70 |

**V4 is the important row and it is not a strategy.** It enters at `close[t-1]`,
hours before the crude bar it trades on exists. It is the naive same-row join
that any date-string merge produces, and it returns +21.74 %/yr at Sharpe 1.97
with t = 6.70 — numbers that would look like a discovery in any writeup. The
honest version of the same signal returns +13.12 % at Sharpe 0.61.

So **roughly two thirds of the apparent edge, and two thirds of the apparent
statistical significance, is unreachable.** That is the cost of the alignment
rule in `build_panel.py`, measured rather than asserted.

To be clear about the project's own history: Phases 1, 2 and 3 did **not** make
this error. Phase 1 used `c[t] → c[t+1]` (entry after the bar closed), Phase 2
used open→close, Phase 3 open→open. V4 was constructed here deliberately as a
control. The audit was worth running — Phase 4's result made Phase 3's execution
timing worth re-checking, and it came back clean.

## 2. Where the money in V1 actually comes from

Decomposing V1 into its two halves is the most useful thing in this phase.

- **V2 (intraday only) is dead on costs.** Gross +0.46 %/yr against 3.31 % of
  cost. The intraday residual Phase 4 measured (ONGC +0.055, Oil India +0.040)
  is real, but it is roughly an order of magnitude too small to survive a daily
  round trip. This closes the "trade the intraday residual" idea completely.
- **V3 (overnight only) is where the money is, and it cannot be harvested
  alone.** Gross +28.15 %/yr — far more than V1's total gross — but isolating it
  requires entering every close and exiting every open, 250 round trips a year,
  which costs 23.98 % and leaves +4.17 %.
- **V1 earns the overnight exposure cheaply by not round-tripping.** Holding
  open-to-open costs 1.97 %/yr instead of 23.98 %.

So V1 is best understood as: *a cheap way to hold overnight crude-momentum
exposure in upstream names*. It is not an intraday signal and never was. Its
edge is a bet that crude bar `t` resembles crude bar `t-1`, collected through the
gap it holds across. That framing matters for live trading — the risk is
overnight gap risk, and the strategy has no ability to react to it.

## 3. The 6-level regime: tested twice, rejected both times

Phase 0's five named regimes are calendar slices chosen with hindsight and
unusable in a live rule. Phase 5 built a causal substitute:

```
vol state    trailing 60d Brent vol vs the EXPANDING 33rd/67th percentile
             of its own history to date                    -> low / mid / high
trend state  sign of trailing 120d Brent cumulative return  -> down / up
regime = vol_state * 2 + trend_state                        -> 6 levels
```

Descriptively the six levels are real and economically sensible — buy-and-hold
upstream by regime, over the full sample:

| regime | % of sample | Brent vol | upstream buy & hold %/yr |
|---|---|---|---|
| low vol / down | 11.4 % | 17.8 | +22.50 |
| low vol / up | 13.6 % | 19.0 | +28.49 |
| mid vol / down | 17.5 % | 29.5 | +12.97 |
| mid vol / up | 15.8 % | 27.2 | +7.14 |
| **high vol / down** | 22.1 % | 49.4 | **−16.52** |
| high vol / up | 19.7 % | 45.4 | +12.88 |

High-volatility falling crude is genuinely the bad state. That is a true fact
about the data. **It still does not make a better strategy.**

Two formulations, both selected inside the walk-forward on training data only:

| | net %/yr | vol | Sharpe | maxDD | t |
|---|---|---|---|---|---|
| V1 no regime conditioning | **+13.12** | 21.5 | **+0.61** | −42.1 | +2.08 |
| V5 6-level on/off filter | +8.52 | 18.3 | +0.47 | −44.7 | +1.59 |
| V6 6-level exposure scaling | +5.19 | 14.3 | +0.36 | −42.2 | +1.24 |

**Conditioning makes it monotonically worse.** The soft version is worse than
the hard version, which is worse than no conditioning at all. That monotonicity
is what makes this a confident rejection rather than a marginal one — if the
regimes carried signal, the gentler formulation should at least have helped.

**The mechanism of the failure is worth recording.** Crude regimes persist for
years. The on/off filter sat out **two entire calendar years**: in 2015 and 2016
the whole test year fell in high-vol states that training had marked as losing.
It dodged 2015's −10.2 % and missed 2016's +27.5 %. With six levels and
multi-year persistence, the filter is not making ~250 decisions a year, it is
making a handful of multi-year bets, and 12 years is nowhere near enough to
judge them. The selected regime set also changed 9 times in 12 years, which is
the usual signature of fitting noise.

**Answer to "include 6-level regimes if required": not required.** The regime
structure is real as a description and should stay in the research, but it must
not be put in the position sizing.

## 4. Vol targeting: reconciled with Phase 3c

Phase 5 initially produced +12.30 %/yr at Sharpe 0.80 for vol-targeted V1,
against Phase 3c's recorded +7.44 % / 0.65. That was not an improvement — it was
a different definition, and both are now printed side by side so the headline
cannot be picked afterwards.

| sizing rule | net %/yr | Sharpe | maxDD |
|---|---|---|---|
| scale by trailing vol of the **asset** (Phase 3c's) | +7.53 | 0.66 | −24.7 |
| scale by trailing vol of the **strategy's net PnL** | +12.30 | 0.80 | −30.1 |

The asset-scaled figure reproduces Phase 3c to within rounding (+7.44 / 0.65 /
−24.8), so Phase 3c is confirmed reproducible. The strategy-scaled version
de-risks less, because the strategy is flat ~35 % of the time and that lowers
its measured volatility. It is not more alpha. **The asset-scaled number remains
the headline**, as the more conservative of the two.

## 5. What to do

- **Keep Phase 3's structure B, unchanged.** Entry at the open, exit at the next
  open, vol-targeted on asset vol to 15 %, leverage capped at 1.0.
- **Do not add the regime filter.** Tested two ways, worse both ways.
- **Do not chase the intraday residual.** Gross 0.46 % against 3.31 % cost.
- **Do not isolate the overnight leg.** Gross 28 % against 24 % cost.
- Paper trade forward, un-tuned. Every in-sample slice is now spent, and Phase 5
  added two more looks at the same data.

## 6. Limits

- V1's t is +2.08 across 12 walk-forward years and 4 of those years lost money
  (worst −27.2 %). Phase 5 did nothing to strengthen that; it only explained it.
- The regime rejection rests on 12 out-of-sample years against a state variable
  that changes every few years. It is the right call on the evidence available,
  but the evidence is thin by construction and would stay thin with more data.
- Costs remain modelled at 10 bps one-way, not measured. V3's verdict is
  especially cost-sensitive: at 2 bps one-way the overnight-only leg would look
  very different, and nobody in this project has priced real NSE open-auction
  fills.
- Cross-feed confirmation is impossible here. The MT5 crude history starts
  2021-10, so a 12-year walk-forward cannot run on it. Phase 4's direction
  signs were confirmed on both feeds; these strategy results are single-feed.
- The regime definition is one of many. Vol terciles and a 120-day trend sign
  were fixed before running and not tuned, which is the right discipline, but a
  different causal regime definition has not been excluded.

## Reproduce

    V=D:/quant/venv/Scripts/python.exe
    $V -I src/phase5_rebuild.py yf
