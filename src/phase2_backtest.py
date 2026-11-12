"""Phase 2: fit on train only, validate, then ONE look at the holdout.

Protocol, fixed before any number was computed
----------------------------------------------
  TRAIN  2010-01-04 .. 2019-12-31   parameters chosen here, by a rule stated
                                    in advance (below). Nothing else.
  VALID  2020-01-01 .. 2023-12-31   sanity check on the chosen parameters.
                                    NOT used to re-choose them.
  HOLD   2024-01-01 .. 2026-11-06   looked at exactly once, at the end.

SELECTION RULE (declared in advance, applied mechanically):
  maximise TRAIN net Sharpe, subject to
    - at least 150 active days in train (no thin-sample flukes)
    - tie-break toward the LARGER hold (lower turnover, more robust)
  The full grid is printed so a spike can be told from a plateau. A parameter
  that is only good at one grid point is a fit, not an edge.

Run on both crude feeds. A result that appears on only one feed is a property
of that feed's bar boundary, not of the market.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.strategy import backtest, build_legs, stats, COST_BPS_ONE_WAY  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

TRAIN = ("2010-01-04", "2019-12-31")
VALID = ("2020-01-01", "2023-12-31")
HOLD = ("2024-01-01", "2026-11-06")

THRESHOLDS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
HOLDS = [1, 2, 3, 5, 10]
MIN_ACTIVE_DAYS = 150

HDR = (f"{'thr':>5} {'hold':>5} {'net%':>7} {'gross%':>7} {'cost%':>6} "
       f"{'vol%':>6} {'Sharpe':>7} {'maxDD%':>7} {'hit%':>6} {'turn':>6} "
       f"{'act%':>6} {'t':>6}")


def row(s: dict, thr: float, h: int) -> str:
    if "sharpe" not in s:
        return f"{thr:>5.2f} {h:>5d}   (insufficient sample: n={s['n']})"
    return (f"{thr:>5.2f} {h:>5d} {s['net_ann']:>7.2f} {s['gross_ann']:>7.2f} "
            f"{s['cost_ann']:>6.2f} {s['vol_ann']:>6.2f} {s['sharpe']:>7.2f} "
            f"{s['max_dd']:>7.2f} {s['hit']:>6.1f} {s['turnover_ann']:>6.1f} "
            f"{s['days_in_mkt']:>6.1f} {s['t_stat']:>6.2f}")


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    variant = sys.argv[2] if len(sys.argv) > 2 else "intraday"
    OUT.mkdir(parents=True, exist_ok=True)

    p = pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")
    p = build_legs(p)

    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    say("=" * 96)
    say(f"PHASE 2 BACKTEST -- long upstream / short OMC, dollar-neutral")
    say(f"crude source: {source}   execution variant: {variant}   "
        f"cost: {COST_BPS_ONE_WAY:.0f} bps one-way")
    say(f"train {TRAIN[0]}..{TRAIN[1]}   valid {VALID[0]}..{VALID[1]}   "
        f"HOLDOUT {HOLD[0]}..{HOLD[1]}")
    say("=" * 96)

    # ---------------- 1. train grid ----------------
    say("")
    say("1. TRAIN GRID (2010-2019). Parameters are chosen HERE and nowhere else.")
    say("   Look for a plateau, not a peak.")
    say("")
    say("   " + HDR)
    tr = p.loc[TRAIN[0]:TRAIN[1]]
    grid = []
    for thr in THRESHOLDS:
        for h in HOLDS:
            bt = backtest(tr, thr, h, variant)
            s = stats(bt, f"thr={thr} hold={h}")
            active = int((bt["pos"] != 0).sum())
            s["active_days"] = active
            s["thr"], s["hold"] = thr, h
            grid.append(s)
            say("   " + row(s, thr, h))
        say("")
    g = pd.DataFrame(grid)

    # ---------------- 2. selection ----------------
    say("-" * 96)
    say("2. SELECTION (rule declared in advance, applied mechanically)")
    elig = g[(g.active_days >= MIN_ACTIVE_DAYS) & g.sharpe.notna()].copy()
    if elig.empty:
        say("   no parameter set meets the minimum-sample requirement. STOP.")
        (OUT / f"phase2_{source}_{variant}.txt").write_text("\n".join(report),
                                                            encoding="utf-8")
        return 1
    best = elig.sort_values(["sharpe", "hold"], ascending=[False, False]).iloc[0]
    thr_s, hold_s = float(best.thr), int(best.hold)
    say(f"   chosen: threshold={thr_s}  hold={hold_s}  "
        f"(train Sharpe {best.sharpe:.2f}, {int(best.active_days)} active days)")

    # plateau diagnostic: how good are the neighbours?
    nb = elig[(elig.thr.between(thr_s - 0.3, thr_s + 0.3))
              & (elig.hold.between(max(1, hold_s - 2), hold_s + 5))]
    say(f"   neighbourhood Sharpe: median {nb.sharpe.median():.2f}, "
        f"min {nb.sharpe.min():.2f}, max {nb.sharpe.max():.2f}, n={len(nb)}")
    frac_pos = float((elig.sharpe > 0).mean())
    say(f"   fraction of the whole grid with positive train Sharpe: {frac_pos:.0%}")
    say("   -> a robust edge shows most of the grid positive and a flat")
    say("      neighbourhood. A lone spike in a mostly-negative grid is a fit.")

    # ---------------- 3. out-of-sample ----------------
    say("")
    say("-" * 96)
    say("3. OUT-OF-SAMPLE at the chosen parameters (NOT re-tuned)")
    say("")
    say("   " + f"{'period':<24}" + HDR[5:])
    periods = [("TRAIN 2010-2019", TRAIN), ("VALID 2020-2023", VALID),
               ("HOLDOUT 2024-2026", HOLD), ("FULL 2010-2026", (TRAIN[0], HOLD[1]))]
    oos = {}
    for label, (a, b) in periods:
        bt = backtest(p.loc[a:b], thr_s, hold_s, variant)
        s = stats(bt, label)
        oos[label] = (s, bt)
        if "sharpe" in s:
            say(f"   {label:<24}" + row(s, thr_s, hold_s)[11:])
        else:
            say(f"   {label:<24} insufficient sample (n={s['n']})")

    # ---------------- 4. cost sensitivity ----------------
    say("")
    say("-" * 96)
    say("4. COST SENSITIVITY on the HOLDOUT (where does the edge die?)")
    say("")
    say(f"   {'cost bps 1-way':>15} {'net%':>8} {'Sharpe':>8}")
    for c in [0.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0]:
        s = stats(backtest(p.loc[HOLD[0]:HOLD[1]], thr_s, hold_s, variant, cost_bps=c))
        if "sharpe" in s:
            say(f"   {c:>15.1f} {s['net_ann']:>8.2f} {s['sharpe']:>8.2f}")

    # ---------------- 5. verdict ----------------
    say("")
    say("=" * 96)
    say("5. VERDICT")
    hs = oos["HOLDOUT 2024-2026"][0]
    vs = oos["VALID 2020-2023"][0]
    say("")
    if "sharpe" not in hs:
        say("   INCONCLUSIVE -- holdout sample too small.")
    else:
        checks = {
            "holdout net return > 0": hs["net_ann"] > 0,
            "holdout Sharpe > 0.5": hs["sharpe"] > 0.5,
            "holdout t-stat > 1.7": hs["t_stat"] > 1.7,
            "valid net return > 0": vs.get("net_ann", -1) > 0,
            "survives 15 bps cost": stats(backtest(
                p.loc[HOLD[0]:HOLD[1]], thr_s, hold_s, variant, cost_bps=15.0)
            ).get("net_ann", -1) > 0,
            "grid mostly positive": frac_pos > 0.6,
        }
        for k, v in checks.items():
            say(f"   [{'PASS' if v else 'FAIL'}] {k}")
        npass = sum(checks.values())
        say("")
        say(f"   {npass}/{len(checks)} checks passed.")
        if npass == len(checks):
            say("   -> PROFITABLE out of sample on this feed and variant. Proceed to")
            say("      Phase 4 robustness (walk-forward, slippage, capacity).")
        elif npass >= 4:
            say("   -> MARGINAL. Real but fragile. Do NOT size this up. Paper trade.")
        else:
            say("   -> NOT PROFITABLE out of sample. The train result was a fit.")
            say("      Do not deploy. Do not re-tune on the holdout -- that burns it.")
    say("=" * 96)

    g.to_csv(OUT / f"phase2_grid_{source}_{variant}.csv", index=False)
    eq = pd.DataFrame({
        lbl: bt["net"].cumsum() for lbl, (_, bt) in oos.items()
        if lbl == "FULL 2010-2026"
    })
    eq.to_csv(OUT / f"phase2_equity_{source}_{variant}.csv")
    (OUT / f"phase2_{source}_{variant}.txt").write_text("\n".join(report),
                                                        encoding="utf-8")
    print(f"\nwrote outputs/phase2_{source}_{variant}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
