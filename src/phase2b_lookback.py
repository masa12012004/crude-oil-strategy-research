"""Phase 2b: add the crude-momentum lookback, selected on TRAIN+VALID only.

Why this script exists, stated plainly
--------------------------------------
Phase 2a (`phase2_backtest.py`) found a large GROSS edge -- up to 24.7%/yr at
threshold 0, hold 1 -- and an almost exactly equal cost bill (25.3%/yr). The
signal works; the implementation hands all of it to the broker. That diagnosis
is visible in the TRAIN grid alone and needs no holdout information.

So this script searches one extra dimension -- the crude momentum lookback --
chosen to cut turnover rather than to raise gross return.

HONEST ACCOUNTING OF HOLDOUT USES
  look 1: phase2_backtest.py, yf, intraday   -> 2/6, failed
  look 2: phase2_backtest.py, yf, overnight  -> 4/6, marginal
  look 3: this script                        -> final
Three looks at the same holdout is multiple testing. The verdict here is
therefore discounted accordingly, and the script reports a Bonferroni-style
adjusted bar rather than pretending a single clean test happened. The 2024+
period is now USED UP. Any further parameter change must be judged on fresh
data (forward paper trading), not on this sample.

Selection here uses TRAIN+VALID (2010-2023) because signal CONSTRUCTION is
allowed to use all non-holdout data. Parameters are still chosen by a rule
declared before the numbers were read.
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

FIT = ("2010-01-04", "2023-12-31")      # train + valid, for construction
TRAIN = ("2010-01-04", "2019-12-31")
VALID = ("2020-01-01", "2023-12-31")
HOLD = ("2024-01-01", "2026-11-06")

LOOKBACKS = [1, 2, 3, 5, 10, 20, 40]
THRESHOLDS = [0.0, 0.5, 0.75, 1.0, 1.5]
HOLDS = [1, 3, 5, 10]
MIN_ACTIVE = 200
N_HOLDOUT_LOOKS = 3


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    variant = sys.argv[2] if len(sys.argv) > 2 else "overnight"
    OUT.mkdir(parents=True, exist_ok=True)
    p = build_legs(
        pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")
    )

    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    say("=" * 92)
    say("PHASE 2b -- crude momentum lookback, long upstream / short OMC")
    say(f"crude source: {source}   variant: {variant}   "
        f"cost {COST_BPS_ONE_WAY:.0f} bps one-way")
    say(f"construction sample {FIT[0]}..{FIT[1]}   HOLDOUT {HOLD[0]}..{HOLD[1]}")
    say("=" * 92)

    # ---------- 1. lookback sweep on the construction sample ----------
    say("")
    say("1. LOOKBACK SWEEP on 2010-2023 (holdout untouched)")
    say("   best (thr, hold) per lookback, by net Sharpe, min "
        f"{MIN_ACTIVE} active days")
    say("")
    say(f"   {'look':>5} {'thr':>5} {'hold':>5} {'net%':>7} {'gross%':>7} "
        f"{'cost%':>6} {'Sharpe':>7} {'maxDD%':>7} {'turn':>6} {'t':>6} "
        f"{'grid+%':>7}")
    fit = p.loc[FIT[0]:FIT[1]]
    rows = []
    for lb in LOOKBACKS:
        cand = []
        for thr in THRESHOLDS:
            for h in HOLDS:
                bt = backtest(fit, thr, h, variant, lookback=lb)
                s = stats(bt)
                if "sharpe" not in s or int((bt["pos"] != 0).sum()) < MIN_ACTIVE:
                    continue
                s.update(lookback=lb, thr=thr, hold=h)
                cand.append(s)
        if not cand:
            say(f"   {lb:>5} -- no eligible parameter set")
            continue
        c = pd.DataFrame(cand)
        b = c.sort_values(["sharpe", "hold"], ascending=[False, False]).iloc[0]
        gp = 100 * float((c.sharpe > 0).mean())
        rows.append(dict(b) | {"grid_pos": gp})
        say(f"   {lb:>5} {b.thr:>5.2f} {int(b.hold):>5} {b.net_ann:>7.2f} "
            f"{b.gross_ann:>7.2f} {b.cost_ann:>6.2f} {b.sharpe:>7.2f} "
            f"{b.max_dd:>7.2f} {b.turnover_ann:>6.1f} {b.t_stat:>6.2f} {gp:>6.0f}%")
    R = pd.DataFrame(rows)
    if R.empty:
        say("   nothing eligible. STOP.")
        return 1

    # ---------- 2. selection ----------
    say("")
    say("-" * 92)
    say("2. SELECTION  (rule: best net Sharpe on 2010-2023, tie-break larger lookback)")
    best = R.sort_values(["sharpe", "lookback"], ascending=[False, False]).iloc[0]
    lb_s, thr_s, h_s = int(best.lookback), float(best.thr), int(best.hold)
    say(f"   chosen: lookback={lb_s}d  threshold={thr_s}  hold={h_s}d")
    say(f"   construction-sample Sharpe {best.sharpe:.2f}  net {best.net_ann:.2f}%/yr  "
        f"turnover {best.turnover_ann:.1f}x/yr")
    say(f"   fraction of that lookback's (thr,hold) grid with positive Sharpe: "
        f"{best.grid_pos:.0f}%")
    say(f"   neighbouring lookbacks' Sharpe: "
        + ", ".join(f"{int(r.lookback)}d={r.sharpe:.2f}" for _, r in R.iterrows()))

    # ---------- 3. period breakdown ----------
    say("")
    say("-" * 92)
    say("3. PERIOD BREAKDOWN at the chosen parameters (no re-tuning)")
    say("")
    say(f"   {'period':<22} {'net%':>7} {'gross%':>7} {'cost%':>6} {'vol%':>6} "
        f"{'Sharpe':>7} {'maxDD%':>7} {'hit%':>6} {'turn':>6} {'t':>6}")
    per = [("TRAIN 2010-2019", TRAIN), ("VALID 2020-2023", VALID),
           ("HOLDOUT 2024-2026", HOLD), ("FULL 2010-2026", (TRAIN[0], HOLD[1]))]
    got = {}
    for label, (a, b) in per:
        bt = backtest(p.loc[a:b], thr_s, h_s, variant, lookback=lb_s)
        s = stats(bt, label)
        got[label] = (s, bt)
        if "sharpe" not in s:
            say(f"   {label:<22} insufficient sample n={s['n']}")
            continue
        say(f"   {label:<22} {s['net_ann']:>7.2f} {s['gross_ann']:>7.2f} "
            f"{s['cost_ann']:>6.2f} {s['vol_ann']:>6.2f} {s['sharpe']:>7.2f} "
            f"{s['max_dd']:>7.2f} {s['hit']:>6.1f} {s['turnover_ann']:>6.1f} "
            f"{s['t_stat']:>6.2f}")

    # calendar-year PnL: is it one lucky year?
    say("")
    say("   calendar-year net return (%), chosen parameters, full sample")
    bt_full = backtest(p, thr_s, h_s, variant, lookback=lb_s)
    yr = bt_full["net"].groupby(bt_full.index.year).sum() * 100
    for y, v in yr.items():
        mark = "  <- holdout" if y >= 2024 else ""
        say(f"     {y}  {v:>7.2f}{mark}")
    say(f"   positive years: {int((yr > 0).sum())}/{len(yr)}")

    # ---------- 4. cost sensitivity ----------
    say("")
    say("-" * 92)
    say("4. COST SENSITIVITY (net %/yr)")
    say("")
    say(f"   {'cost bps':>9} {'2010-2023':>11} {'HOLDOUT':>11} {'FULL':>11}")
    for c in [0.0, 5.0, 10.0, 15.0, 20.0, 30.0]:
        vals = []
        for a, b in [FIT, HOLD, (TRAIN[0], HOLD[1])]:
            s = stats(backtest(p.loc[a:b], thr_s, h_s, variant,
                               cost_bps=c, lookback=lb_s))
            vals.append(s.get("net_ann", float("nan")))
        say(f"   {c:>9.1f} {vals[0]:>11.2f} {vals[1]:>11.2f} {vals[2]:>11.2f}")

    # ---------- 5. verdict, multiplicity-adjusted ----------
    say("")
    say("=" * 92)
    say("5. VERDICT")
    hs, _ = got["HOLDOUT 2024-2026"]
    fs = stats(backtest(p.loc[FIT[0]:FIT[1]], thr_s, h_s, variant, lookback=lb_s))
    # with 3 looks at the holdout, require a correspondingly higher bar
    bar_t = 2.4  # ~ two-sided 5% Bonferroni over 3 looks
    say("")
    say(f"   holdout has now been examined {N_HOLDOUT_LOOKS} times, so the")
    say(f"   significance bar is raised from t>1.7 to t>{bar_t} (Bonferroni over")
    say("   3 looks). This is not a technicality -- it is why the 2024+ sample")
    say("   is now spent.")
    say("")
    if "sharpe" not in hs:
        say("   INCONCLUSIVE -- holdout too small.")
        npass = tot = 0
    else:
        checks = {
            "construction-sample net > 0": fs.get("net_ann", -1) > 0,
            "construction-sample Sharpe > 0.4": fs.get("sharpe", -1) > 0.4,
            "holdout net > 0": hs["net_ann"] > 0,
            "holdout Sharpe > 0.5": hs["sharpe"] > 0.5,
            f"holdout t > {bar_t}": hs["t_stat"] > bar_t,
            "survives 20 bps cost (full)": stats(backtest(
                p, thr_s, h_s, variant, cost_bps=20.0, lookback=lb_s)
            ).get("net_ann", -1) > 0,
            "positive in >=60% of years": float((yr > 0).mean()) >= 0.6,
            "maxDD shallower than 1yr net": abs(hs["max_dd"]) < max(hs["net_ann"], 1e-9),
        }
        for k, v in checks.items():
            say(f"   [{'PASS' if v else 'FAIL'}] {k}")
        npass, tot = sum(checks.values()), len(checks)
        say("")
        say(f"   {npass}/{tot} checks passed.")
    say("")
    if tot and npass == tot:
        say("   -> PROFITABLE and robust. Proceed to Phase 4/5 (walk-forward, paper).")
    elif tot and npass >= tot - 2:
        say("   -> MARGINALLY PROFITABLE. The edge is real but thin relative to cost.")
        say("      Appropriate next step is forward paper trading, not capital.")
    else:
        say("   -> NOT DEMONSTRATED PROFITABLE. Do not deploy capital.")
    say("=" * 92)

    R.to_csv(OUT / f"phase2b_lookback_{source}_{variant}.csv", index=False)
    (OUT / f"phase2b_{source}_{variant}.txt").write_text("\n".join(report),
                                                         encoding="utf-8")
    print(f"\nwrote outputs/phase2b_{source}_{variant}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
