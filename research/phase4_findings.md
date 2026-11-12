> Archived author research note. Figures and conclusions have not been independently reproduced for publication. Referenced local outputs are not bundled.

# Phase 4 — volatility and direction of each OMC/upstream name vs crude

Run date: 2026-11-09. Script: `src/phase4_direction.py` (run on both feeds).
Outputs: `outputs/phase4_direction_{yf,mt5}.csv`, `outputs/phase4_viz_{yf,mt5}.json`,
`outputs/crude_direction.html`.

## What this phase is, and is not

This is a **measurement** phase, not a strategy phase. Phase 1 already established
that crude does not predict OMC close-to-close returns. The question here is
different: *given* that crude moves, which way does each stock move, how big is
the move relative to its own volatility, and is that direction stable?

Two alignments are computed and reported side by side, because conflating them
is the easiest way to manufacture an edge in this dataset:

| alignment | definition | tradable? |
|---|---|---|
| **same-day** | crude bar dated D vs NSE day D | **No.** The D bar closes ~03:30 IST on D+1, after the NSE close on D. |
| **previous bar** | crude bar D−1 vs NSE day D | Yes — this is the panel's standard lookahead-safe alignment. |

Sanity check in the script output: `corr(same-day, previous-bar) = +0.011`, as it
must be, since they are different days.

## 1. Full sample (yfinance feed, 3,999 matched days, 2010–2026)

| asset | vol %/yr | × Brent | beta same-day | t | beta prev bar | t | agree % |
|---|---|---|---|---|---|---|---|
| IOC | 30.3 | 0.82 | −0.004 | −0.3 | −0.033 | −2.6 | 49.3 |
| HPCL | 37.9 | 1.02 | −0.047 | −2.9 | −0.107 | −6.9 | 48.9 |
| BPCL | 33.5 | 0.90 | −0.009 | −0.6 | −0.054 | −4.0 | 49.3 |
| ONGC | 31.8 | 0.86 | **+0.113** | 8.4 | +0.184 | 14.3 | 52.5 |
| Oil India | 33.2 | 0.90 | **+0.087** | 6.1 | +0.159 | 11.8 | 50.6 |
| Nifty 50 | 16.5 | 0.44 | +0.047 | 6.7 | +0.021 | 3.0 | 52.6 |

Brent's own volatility is **37.1 %/yr**. Every Indian oil name is *less* volatile
than the barrel; only HPCL comes close (1.02×).

**The direction splits cleanly by business model.** Upstream producers sell crude
and rise with it. Refiners buy crude and, if anything, lean against it. This is
the same split Phase 1 stumbled on and Phase 3 eventually traded.

**Sign agreement is the sobering column.** Even ONGC — the strongest relationship
on the page — moves the same direction as crude on only 52.5 % of days. These are
weak daily relationships visible in averages, not day-to-day rules.

## 2. Cross-feed confirmation

The MT5 feed (UKOIL, 2021-10 onward, 1,236 matched days) reproduces every sign:

| asset | yf beta (same-day) | mt5 beta (same-day) |
|---|---|---|
| IOC | −0.004 | −0.051 |
| HPCL | −0.047 | −0.104 |
| BPCL | −0.009 | −0.059 |
| ONGC | +0.113 | +0.089 |
| Oil India | +0.087 | +0.106 |

Signs agree 6/6. The refiner negativity is *stronger* on MT5, which is expected —
that feed only covers 2021+, which is where the negative regime lives. This is a
genuine cross-feed check, not a restatement: the two feeds cut the daily bar at
different hours and their daily returns correlate only ~0.89.

## 3. The refiner direction is not stable — it flips

Same-day beta by regime:

| asset | pre_dereg | post_dereg | covid | war_discount | 2024– |
|---|---|---|---|---|---|
| IOC | +0.007 (0.2) | −0.008 (−0.3) | +0.100 (3.8) | +0.005 (0.2) | **−0.134 (−4.8)** |
| HPCL | +0.015 (0.3) | −0.005 (−0.2) | +0.004 (0.1) | −0.065 (−1.6) | **−0.190 (−5.5)** |
| BPCL | +0.062 (1.4) | +0.024 (0.9) | +0.041 (1.1) | −0.025 (−0.9) | **−0.142 (−4.9)** |
| ONGC | +0.086 (2.3) | +0.095 (4.2) | +0.192 (4.8) | +0.105 (3.1) | +0.065 (2.3) |
| Oil India | +0.012 (0.4) | +0.066 (3.1) | +0.112 (2.8) | +0.102 (2.4) | +0.115 (3.1) |
| Nifty 50 | +0.158 (7.4) | +0.043 (4.1) | +0.114 (5.2) | −0.005 (−0.3) | −0.051 (−4.0) |

**Upstream is stable: positive and significant in 4 of 5 regimes, never negative.**
That stability is why Phase 3's surviving structure is an upstream structure.

**Refiners are not stable: near zero for a decade, then firmly negative from 2024**,
all three at |t| > 4.8. The administered-pricing story fits — crude up, pump prices
held, refiner absorbs the margin squeeze — but 2024–2026 is a single regime and one
regime is not a law. A flipping sign is worse than a weak one: a hedge sized on the
old sign works backwards after the flip.

Note the Nifty itself flips sign in the same window, so part of the refiner flip may
be a broad-market effect rather than anything specific to refining.

## 4. The response is already in the opening print

This is the most decision-relevant result in the phase, and it resolves a tension.

The previous-bar beta for HPCL is −0.107 with **t = −6.9**, and the decile pattern is
monotone (crude-move decile 1 → HPCL +0.52 %, decile 10 → −0.40 %). Winsorising at
1/99 % leaves the t essentially unchanged (−6.80), so it is not a tail artefact.
That looks like a real, tradable relationship — and it contradicts Phase 1.

It does not, once the trading day is split. Crude bar D−1 closes ~03:30 IST on day D:
**after** the NSE close on D−1, **before** the NSE open on D. Regressing each part of
the stock's day on that bar:

| asset | full close-to-close | gap c[t−1]→o[t] | intraday o[t]→c[t] | gap share |
|---|---|---|---|---|
| IOC | −0.033 (−2.6) | −0.027 (−4.4) | −0.005 (−0.4) | 84 % |
| HPCL | −0.107 (−6.9) | −0.075 (−10.9) | −0.032 (−2.2) | 70 % |
| BPCL | −0.054 (−4.0) | −0.057 (−9.4) | +0.002 (0.2) | 104 % |
| ONGC | +0.184 (14.3) | +0.129 (21.1) | +0.055 (4.6) | 70 % |
| Oil India | +0.159 (11.8) | +0.119 (18.7) | +0.040 (3.1) | 75 % |
| Nifty 50 | +0.021 (3.0) | +0.027 (6.7) | −0.006 (−1.1) | 128 % |

**70–104 % of the crude response is in the overnight gap.** By the time the market
opens, the move has happened. Phase 1 tested close-to-close from the NSE close of
day t, which is *after* the gap on t and *before* the gap on t+1 — so it was
measuring the intraday residual, and correctly found nothing much.

To capture the gap you must be positioned overnight, which means wearing the
overnight risk of everything else that moves markets, against a beta of 0.03–0.13.
That is not a free lunch; it is a different trade with a different risk profile,
and it is the honest reading of why the effect is "real but uncapturable" in the
way this project has been testing.

The upstream names are the only ones with a surviving intraday component
(ONGC +0.055, t = 4.6; Oil India +0.040, t = 3.1). Small, but non-zero — and
consistent with Phase 3's structure B being an upstream trade.

## 5. What changed in my view of the project

- The original premise is dead in a more precise way than before. It is not that
  crude and OMCs are unrelated — recently they are *inversely* related, strongly.
  It is that the relationship arrives overnight and is gone by the open.
- The upstream/refiner split is now confirmed on two independent feeds and across
  five regimes, which is the firmest structural fact this project has produced.
- Anyone wanting to revive the OMC side should test an **open-to-open** or
  **gap-capture** structure, not another close-to-close signal. That is a genuinely
  different test and has not been run. It would need overnight-risk budgeting and
  realistic open-auction fills, neither of which is modelled anywhere here.

## 6. Limits

- Same-day betas are descriptive only and must never be quoted as signal strength.
- t-statistics are OLS and unadjusted for autocorrelation or heteroskedasticity;
  daily equity returns have both, so treat marginal cases (|t| near 2) as weaker
  than they look. The large values (|t| > 6) survive any reasonable adjustment.
- Beta is measured against Brent **in dollars**. An Indian refiner pays in rupees,
  so part of the measured sensitivity is USDINR. `brent_inr_ret` exists in the panel
  and this decomposition has not been run.
- The gap regression uses yfinance opens, which for NSE names are the first
  auction print. Real fills at the open differ, sometimes materially.
- Regime boundaries were fixed in Phase 0 and not re-chosen here, which is the
  right way round, but they are still only five arbitrary slices.

## Reproduce

    V=D:/quant/venv/Scripts/python.exe
    $V -I src/phase4_direction.py yf
    $V -I src/phase4_direction.py mt5
