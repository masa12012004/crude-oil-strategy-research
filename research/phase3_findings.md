> Archived author research note. Figures and conclusions have not been independently reproduced for publication. Referenced local outputs are not bundled.

# Phase 1c + 3 — findings and final verdict

Run date: 2026-11-09. Scripts: `src/fetch_products.py`, `src/phase1c_crack.py`,
`src/phase3_walkforward.py`, `src/phase3b_benchmark.py`,
`src/phase3c_voltarget.py`. Reports in `outputs/`.

## Verdict

**One structure survived, and it is not the one the project set out to build.**

> **Long/flat ONGC + Oil India, timed by Brent momentum, vol-targeted to 15%.**
> 12-year walk-forward: **+7.4 %/yr net, Sharpe 0.65, maxDD −24.8 %**, 8/12
> positive years, alpha over its own upstream beta **+8.5 %/yr (t = 2.03)**,
> 99.4th percentile against random timing with an identical exposure profile
> (p = 0.006). 5/6 checks passed.

There are **no OMCs in it.** IOC, HPCL and BPCL — the entire original premise —
failed every test in every phase. The tradable relationship was the one Phase 1
found by accident: crude's *positive* beta to upstream producers.

## 1. Phase 1c: the refining-margin hypothesis failed

Phase 2 recommended modelling the mechanism (crude → refining margin → OMC
earnings) rather than the price. I built the 3-2-1 crack spread from RBOB and
heating-oil futures — `(2·RBOB + HO)·42/3 − WTI`, mean $23.1/bbl, range
$2.4–75.3, which is the standard refining-margin measure.

The test was well-posed: the crack is genuinely **independent** of crude
(correlation with Brent returns just 0.166), so this was new information and not
Phase 1 repackaged. It still failed.

Crack-spread IC against the OMC basket, overlap-corrected t in brackets:

| signal | 1d | 5d | 21d | 63d |
|---|---|---|---|---|
| crack 1d change | −0.008 (−0.5) | +0.019 (0.6) | −0.002 (0.0) | −0.011 (−0.1) |
| crack 5d change | +0.026 (1.7) | +0.010 (0.3) | −0.006 (−0.1) | −0.010 (−0.1) |
| crack 21d change | −0.007 (−0.5) | −0.025 (−0.7) | −0.026 (−0.4) | −0.028 (−0.2) |
| crack level z | +0.008 (0.5) | −0.005 (−0.1) | −0.032 (−0.4) | −0.058 (−0.5) |

Nothing. My stated hypothesis — crack up → OMC margins up → OMCs outperform, a
*positive* beta — is unsupported at every horizon.

**And the horizon idea died with it.** Phase 2 recommended raising the horizon to
escape transaction costs. Across all five signals and all eight targets, every
single 5d/21d/63d cell has |t| < 1.5. There is nothing at weekly, monthly or
quarterly frequency. That closes two of the four options Phase 2 proposed.

Note the t-stats above are corrected for overlapping windows (n_eff = n/h).
Uncorrected, several of these would have looked significant — that inflation is
how most multi-horizon studies accidentally find edges.

## 2. Phase 3: walk-forward, because the holdout was spent

With 2024–2026 burned by Phase 2's three looks, validation moved to expanding-
window walk-forward: parameters re-selected before each year on prior data only,
then traded through that year untouched. 12 out-of-sample years, 2015–2026.

| | structure | net %/yr | Sharpe | maxDD | t | +years |
|---|---|---|---|---|---|---|
| A | long UP / short OMC on Brent (Phase 2's) | −0.09 | −0.01 | −28.9 | −0.03 | 7/12 |
| B | **long/flat upstream on Brent** | **+13.12** | **0.61** | −42.1 | **2.08** | 8/12 |
| C | long/flat upstream on crack | +2.08 | 0.15 | −56.0 | 0.50 | 5/12 |

Structure A — the one Phase 1 authorised and Phase 2 built — is confirmed dead
under honest walk-forward: net −0.09 %/yr. Removing the short OMC leg is what
rescued the trade, by cutting cost from 4.58 % to 1.97 %/yr.

## 3. Phase 3b: is B just upstream beta? No

This was the decisive test. B is long-only and in the market 63 % of the time, so
it could easily have been equity beta with extra steps.

| | net %/yr | vol | Sharpe | maxDD |
|---|---|---|---|---|
| structure B | 13.12 | 21.5 | **0.61** | −42.1 |
| buy & hold ONGC+OIL | 8.72 | 30.5 | 0.29 | −116.0 |
| buy & hold Nifty | 9.41 | 16.3 | 0.58 | −48.5 |

- Regressing B on upstream returns: beta 0.526 (≈ its 0.53 average exposure, as
  expected), **alpha +8.54 %/yr, t = 2.03.**
- Block-bootstrap random-timing control (2,000 draws, B's exact exposure profile
  shuffled in 21-day blocks): random mean +1.85 %/yr, 95th percentile +9.04 %.
  B's actual +13.12 % sits at the **99.4th percentile, p = 0.006.**

5/5 checks passed. The timing is real, not beta and not luck.

## 4. Phase 3c: vol-targeting fixes the risk, and buys no edge

B's one failure was risk: Sharpe 0.61 barely beat the Nifty's 0.58, with a 42 %
drawdown. Applied one pre-specified overlay — scale by 15 %/realised vol, 60-day
backward window, **leverage capped at 1.0 so it can only de-risk** (uncapped
vol-targeting gears up in calm markets, which flatters a backtest).

| | net %/yr | vol | Sharpe | maxDD | Calmar |
|---|---|---|---|---|---|
| B raw | 13.12 | 21.5 | 0.61 | −42.1 | 0.31 |
| **B vol-targeted** | **7.44** | **11.5** | **0.65** | **−24.8** | 0.30 |
| Nifty | 9.41 | 16.3 | 0.58 | −48.5 | 0.19 |

Drawdown nearly halved, Sharpe marginally up, **Calmar unchanged at 0.30.** Read
that honestly: vol-targeting did not add edge. It let the same edge be held at a
size you can actually live with. That is worth having and it is not alpha.

The remaining failed check — "maxDD shallower than annual net" — cannot be passed
by any Sharpe-0.65 strategy and should be read as a statement about the strategy's
modest quality, not as a defect to engineer away.

## 5. Honest limits

- **Sharpe 0.65 vs the Nifty's 0.58 is a thin margin.** Twelve years of
  walk-forward, alpha t = 2.03, p = 0.006 against random timing — the effect is
  real, but it is not large, and 2.03 is barely over the bar.
- **Two concentrated positions.** ONGC and Oil India are both Indian oil PSUs,
  heavily correlated, both exposed to government divestment policy, subsidy
  sharing and crude-realisation caps that no price signal can see.
- **Parameter churn.** The walk-forward selected lookbacks of 1, 3, 20 and 40
  days across 12 years. That instability is a real caution: the selection rule
  is not converging on a stable truth.
- **Single-feed confirmation only.** The MT5 panel cannot cross-check Phase 3 —
  it has no pre-2021 history, so a 12-year walk-forward is impossible on it.
  Phase 2c showed the feeds agree closely (86.5 % identical positions), so this
  is a moderate rather than severe caveat.
- **4 of 12 years lost money**, worst −17.9 %. This is not a smooth equity curve.
- **US crack proxy ≠ Indian margin.** Only relevant to the failed Phase 1c, but
  worth stating: the negative result there is weaker evidence than it looks,
  because Indian refiners run a different crude slate and since 2022 a Russian
  discount the US crack cannot see. An actual Singapore GRM / Brent-Dubai series
  could in principle revive the margin hypothesis.
- **No live costs.** 10 bps one-way is modelled, not measured. ONGC and OIL are
  liquid, so this should hold at modest size, but it is an assumption.

## 6. Recommendation

Paper trade the vol-targeted structure B forward, un-tuned, and log it from
today. Fix the parameters by the walk-forward's own last selection rather than
re-optimising. Twelve months of forward data is the only clean test left in this
project — every in-sample slice has now been used.

Do not commit capital on this result alone. A Sharpe-0.65, 25 %-drawdown
strategy on two correlated PSU names deserves a small sleeve at most, and only
after forward confirmation.

If you want to improve it rather than deploy it, the single highest-value step is
real Indian refining-margin data (Singapore GRM, Brent–Dubai differential,
Russian discount). Phase 1c failed on a US proxy; it has not been fairly tested
on the actual Indian margin, and that remains the one untested link in the
economic chain.

## Reproduce

    V=D:/quant/venv/Scripts/python.exe
    $V -I src/fetch_products.py
    $V -I src/build_panel.py yf
    $V -I src/phase1c_crack.py yf
    $V -I src/phase3_walkforward.py yf
    $V -I src/phase3b_benchmark.py yf
    $V -I src/phase3c_voltarget.py yf
