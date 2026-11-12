> Archived author research note. Figures and conclusions have not been independently reproduced for publication. Referenced local outputs are not bundled.

# Phase 1 — method and gate

Phase 1 is **measurement only**. No positions, no parameter search, no PnL. The
output is a single decision: is there enough crude→OMC information to justify
building a strategy?

## The timing problem, stated precisely

| event | time (IST) |
|---|---|
| MT5 crude daily bar `D` opens | 03:30 on `D` |
| NSE cash opens on day `D` | 09:15 |
| NSE cash closes on day `D` | 15:30 |
| MT5 crude daily bar `D` **closes** | 03:30 on `D+1` |

So crude bar `D` finishes *after* the NSE close on day `D`. A date-string join of
crude bar `D` to NSE day `D` therefore embeds roughly 12 hours of future
information — including the US session reaction, which is exactly the part that
matters.

`build_panel.py` handles this by stamping each crude bar with
`avail_date = bar_date + 1 day` and doing a backward `merge_asof` onto the NSE
trading calendar. Consequence: `panel.brent_ret` at row `t` is the return of
crude bar `t-1` over bar `t-2`, and it is known well before any NSE price on
day `t`.

## Two honest execution styles

- **open-exec** — signal from crude bar `t-1` (closed 03:30 IST), trade the NSE
  open at 09:15, exit at the close. ~6h gap. This is the freshest legitimate use
  of a crude daily bar and the variant most likely to work.
- **close-exec** — signal from crude bar `t-1`, trade the NSE close on `t`, exit
  at the close on `t+1`. ~36h gap. Easier to execute, weaker signal.

The report measures both. If only close-exec works, be suspicious.

## What each section answers

- **A** — the same-date (contaminated) correlation. Reported *only* to establish
  the sign of the economic relationship and to show how much of the apparent
  correlation is timezone artefact. Compare A against C: the difference is the
  lookahead you would have booked as alpha.
- **B** — lead/lag scan. If the IC peaks at the contaminated shift and collapses
  at every clean shift, the relationship is contemporaneous only, i.e. crude
  *explains* OMC moves but does not *predict* them. That is the most likely
  outcome and it is not tradable with 1D bars.
- **C** — the gate number, by regime. Regimes matter because the OMC crude beta
  is policy-dependent (admin pricing pre-2014, price freezes, inventory-gain
  quarters). An IC that is strong in two regimes and reversed in two is noise.
- **D** — rolling 250d correlation. `std` and `%neg` are the sign-stability
  measures. A beta whose sign flips cannot be traded directionally without a
  regime filter, which Phase 1 is not allowed to fit.
- **E** — the gate.

## Gate criterion

Proceed to Phase 2 only if some (signal, name, exec) triple has:

- `|Spearman IC| >= 0.03` on the full sample, **and**
- the same IC sign in at least 4 of the 5 regimes.

0.03 is deliberately low — with ~4,100 daily observations an IC of 0.03 is about
2σ, and after NSE costs (brokerage + STT + impact, call it 15–25 bps round trip
on these names) a daily-rebalanced 1D signal needs roughly `IC × σ_ret` to clear
costs. At `σ_ret ≈ 2%` daily for OMCs, IC 0.03 ≈ 6 bps of expected edge per
trade. **That does not clear costs on its own.** So the gate is a test for
"is there anything here at all", not "is this profitable". Clearing it means
Phase 2 is worth attempting with lower turnover (5d holding, threshold entries),
not that a daily system is viable.

## Interpreting a FAIL

A fail is a real result, not a bug. The honest conclusions available are:

1. Crude is contemporaneously but not predictively related to OMCs — the Indian
   market has already priced the overnight crude move into the open. Check by
   looking at whether the IC concentrates in `prev_close → open` (a gap the open-exec
   style cannot capture because it *starts* at the open).
2. Policy and refining-margin news dominate at the daily horizon, and OHLCV
   cannot see them.
3. The horizon is wrong — crude→margin→earnings is a quarterly transmission, so
   a weekly/monthly signal on crude *levels* (not returns) may carry information
   that a 1d return does not.

If Phase 1 fails, (3) is the most promising redefinition and the natural Phase 1b.

## Known caveats in this run

- yfinance `auto_adjust=True` adjusts for dividends as well as splits. IOC, BPCL
  and ONGC are high-dividend PSUs, so the adjusted series is a total-return
  series. For a return-prediction study this is the consistent choice, but it is
  not what a price-only backtest would trade. Revisit at Phase 3.
- The NSE trading calendar is inferred from the price data, not from an official
  holiday list. Good enough for IC; tighten before Phase 3.
- Exness `UKOIL`/`USOIL` are CFDs on the front future, with broker-specific
  rollover. Roll days will show as artificial gaps in the crude return series.
  Not material for rank IC; material for any crude-level signal.
