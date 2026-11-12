> Archived author research note. Figures and conclusions have not been independently reproduced for publication. Referenced local outputs are not bundled.

# Phase 1 — findings and gate decision

Run date: 2026-11-08. Sample: 2010-01-04 → 2026-11-06, 4,159 NSE trading days.
Scripts: `src/phase1_ic.py`, `src/phase1b_spread.py`. Raw reports in `outputs/`.

## Verdict

**CONDITIONAL PASS — but not for the strategy as originally specified.**

The crude signal does not predict the OMC basket. It predicts the *spread*
between upstream producers and OMCs. Phase 2 is authorised for that structure
only.

## 1. The original premise does not hold

Crude's same-day relationship to the three OMCs is essentially zero:

| name | same-day corr (2010–26) | rolling-250d mean | % of time negative |
|---|---|---|---|
| IOC | −0.005 | −0.008 | 59% |
| HINDPETRO | −0.046 | −0.036 | 68% |
| BPCL | −0.009 | +0.004 | 37% |
| **OMC basket** | **−0.024** | **−0.015** | **54%** |
| ONGC | **+0.131** | **+0.108** | **11%** |
| OIL | **+0.096** | **+0.069** | **12%** |

The sign is negative for OMCs, as predicted from the cost-input argument, but the
magnitude is negligible and the sign flips roughly half the time. The upstream
names are the opposite: a clearly positive beta that holds ~89% of the time.

So the stable crude-sensitive assets on NSE are **ONGC and Oil India**, not the
OMCs. The OMC crude beta is swamped by policy (price freezes, excise, subsidy)
and by refining-margin dynamics that crude alone does not capture.

## 2. Crude explains OMC moves; it does not predict them

Lead/lag scan on the basket (`yf` source):

| shift | IC | p | status |
|---|---|---|---|
| 0 (overlapping window) | −0.0916 | 0.000 | **not tradable** |
| +1 | +0.0074 | 0.635 | clean |
| +2 | +0.0038 | 0.807 | clean |
| +3 | −0.0115 | 0.457 | clean |
| +4 | +0.0406 | 0.009 | clean, but 1 of 9 tests |
| +5 | −0.0048 | 0.758 | clean |

Every clean lag is indistinguishable from zero. The one apparently significant
value (+4) is what you expect from nine simultaneous tests and should not be
believed. This is the single most important negative result in Phase 1:
**close-to-close execution has no edge.** The close-exec IC table in section C
confirms it — every name, every signal, |IC| < 0.011, p > 0.5.

The information lives entirely in the overlapping window, i.e. crude explains
the NSE move that has already happened.

## 3. Open-execution is where the (small) edge is

Signal from the crude bar that closes 03:30 IST, traded at the 09:15 open and
held to the close:

| leg | IC (2010–26) | IC (2021–26) | p | regime sign agreement |
|---|---|---|---|---|
| long upstream | +0.070 | +0.129 | 0.000 | 4/5 |
| long OMC basket | −0.025 | −0.038 | 0.101 | 4/5 |
| **upstream − OMC spread** | **+0.101** | **+0.153** | **0.000** | **4/5** |
| ONGC − HINDPETRO | +0.092 | +0.136 | 0.000 | 4/5 |

The spread beats both legs, on both independent data sources, over both samples.
That is the expected signature of a genuine relative-value effect: the common
factor (Nifty / PSU beta / risk-on) carries the same sign in both legs and
cancels, while the crude-driven component is opposite-signed and adds.

The one regime that disagrees is covid (−0.029), where the OMC crude beta flipped
strongly positive (+0.187) — inventory gains on cheap crude inventory. That is a
known, explicable mechanism, not noise, and it is the main risk to the structure.

## 4. Costs bite hard

Expected edge per trade ≈ IC × σ(target). NSE round-trip on these names is
roughly 15–25 bps all-in.

| leg | edge | verdict |
|---|---|---|
| long upstream | 11 bps | below cost |
| long OMC | 5 bps | below cost |
| upstream − OMC | 18 bps | marginal |
| ONGC − HINDPETRO | 21 bps | marginal |

A daily-rebalanced version of this does not survive costs even where the IC is
real. Phase 2 must use threshold entries and multi-day holds so the edge is drawn
from a larger crude move while cost is paid once. This is a constraint, not a
tuning knob — and note that choosing the threshold is exactly where overfitting
will enter, so it must be set on a training window and never revisited.

## 5. Data integrity findings

- **MT5 history is too short.** The Exness demo server retains crude back only to
  2021-10-27 (1,299 bars). The regime test needs 2010+, so ICE Brent `BZ=F` and
  NYMEX WTI `CL=F` from yfinance were added as the history source
  (`src/fetch_crude_yf.py`), with MT5 kept as the live/verification feed.
- **The two crude feeds are not interchangeable.** `src/validate_crude.py`:
  close levels correlate 0.9964, but daily *returns* only 0.888 (Brent) and 0.812
  (WTI), because the two feeds cut the daily bar at different hours. Every Phase 1
  number is therefore computed twice, once per source, and only conclusions that
  hold on both are recorded here. **This is also a live-trading constraint:** the
  system must trade off whichever feed it was validated on.
- **WTI went negative** on 2020-04-20 (−37.63 settle), which breaks log returns.
  `build_panel.py` masks an 8-bar window around it rather than propagating NaN.
- The `phase1_ic.py` gate printed FAIL on the `mt5` panel. That is mechanical, not
  evidence: with data only from 2021 only two of five regimes are populated, so
  the "≥4 of 5 regimes agree" criterion is unreachable by construction. The
  `mt5` ICs themselves are *stronger* than `yf`. Do not read that FAIL as a
  contradiction.
- **The three OMCs are one bet**, as suspected: pairwise daily return correlation
  IOC/HINDPETRO 0.733, HINDPETRO/BPCL 0.783, IOC/BPCL 0.710. Size the basket.

## 6. Mandate for Phase 2

Authorised:

- Structure: **long upstream (ONGC, OIL) / short OMC basket**, dollar-neutral,
  signalled by the previous crude bar's return.
- Execution: enter at the NSE open, not the close. Close-exec is dead.
- Turnover: threshold entry + multi-day hold. Fix the threshold on 2010–2019 and
  never refit it.
- Out-of-sample reserve: **2024-01-01 onward is not to be looked at** until the
  Phase 3 backtest is frozen.

Not authorised:

- Long-only OMC directional trading on crude. Phase 1 says there is no edge there.
- Any close-to-close version.
- Daily rebalancing.

Open question for Phase 2: the short OMC leg needs stock futures or SLB, since
NSE cash does not permit overnight shorts. IOC, BPCL and HINDPETRO are all in the
F&O segment, so futures are available — but that changes the cost model and adds
roll and basis risk. Re-run the cost check against futures costs before building.
