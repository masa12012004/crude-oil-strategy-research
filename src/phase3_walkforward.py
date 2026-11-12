"""Phase 3: expanding-window walk-forward. The definitive test.

Why walk-forward and not a holdout
----------------------------------
Phase 2 examined the 2024-2026 holdout three times, so it is spent. Walk-forward
has no reserved slice to burn: at each year boundary, parameters are selected on
everything strictly BEFORE that boundary and then traded through the following
year, untouched. Concatenating those years gives one out-of-sample track record
in which every trade was made with information available at the time.

This is a harder test than a single holdout and it cannot be gamed by re-running,
because re-running re-selects honestly at every step.

Three candidate structures, all that survived Phases 1-1c:
  A  SPREAD  long upstream / short OMC, on brent momentum   (Phase 2's structure)
  B  UP      long/flat upstream only, on brent momentum     (no short leg, no
             futures cost -- Phase 2 section 7 option 3)
  C  UP      long/flat upstream only, on crack momentum     (Phase 1c's only
             cell with |t| > 2 that was not just crude again)

Reported honestly: a walk-forward Sharpe below ~0.5 net, or a drawdown deeper
than the annual return, means do not deploy.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.strategy import build_legs, stats, COST_BPS_ONE_WAY  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

LOOKBACKS = [1, 3, 5, 10, 20, 40]
THRESHOLDS = [0.0, 0.5, 0.75, 1.0, 1.5]
HOLDS = [1, 3, 5, 10]
MIN_TRAIN_YEARS = 5
MIN_ACTIVE = 150


def make_signal(p: pd.DataFrame, sig_col: str, lookback: int,
                threshold: float, hold: int, long_only: bool,
                vol_window: int = 60) -> pd.Series:
    mom = p[sig_col].rolling(lookback).sum()
    z = mom / mom.rolling(vol_window).std()
    raw = np.sign(z).where(z.abs() >= threshold, 0.0)
    if long_only:
        raw = raw.clip(lower=0.0)
    return raw.rolling(hold).mean().fillna(0.0).clip(-1.0, 1.0)


def run(p: pd.DataFrame, struct: str, sig_col: str, lookback: int,
        threshold: float, hold: int, cost_bps: float = COST_BPS_ONE_WAY) -> pd.DataFrame:
    long_only = struct != "SPREAD"
    pos = make_signal(p, sig_col, lookback, threshold, hold, long_only)
    ret = p["spread_o2o"] if struct == "SPREAD" else p["UP_o2o"]
    turnover = pos.diff().abs().fillna(pos.abs())
    gross = pos * ret
    cost = turnover * cost_bps / 1e4
    return pd.DataFrame({"pos": pos, "ret": ret, "gross": gross,
                         "turnover": turnover, "cost": cost,
                         "net": gross - cost}, index=p.index).dropna(subset=["ret"])


def select(train: pd.DataFrame, struct: str, sig_col: str):
    """Pick parameters on train only, by net Sharpe, tie-break larger hold."""
    best, best_key = None, None
    for lb in LOOKBACKS:
        for thr in THRESHOLDS:
            for h in HOLDS:
                bt = run(train, struct, sig_col, lb, thr, h)
                if int((bt["pos"] != 0).sum()) < MIN_ACTIVE:
                    continue
                s = stats(bt)
                if "sharpe" not in s or np.isnan(s["sharpe"]):
                    continue
                key = (s["sharpe"], h, lb)
                if best_key is None or key > best_key:
                    best_key, best = key, (lb, thr, h, s["sharpe"])
    return best


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    OUT.mkdir(parents=True, exist_ok=True)
    p = build_legs(
        pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")
    )
    p["UP_ret"] = p[["ONGC_ret", "OIL_ret"]].mean(axis=1)

    CANDIDATES = [
        ("A", "SPREAD", "brent_ret", "long UP / short OMC on brent momentum"),
        ("B", "UP", "brent_ret", "long/flat upstream on brent momentum"),
        ("C", "UP", "crack321_chg", "long/flat upstream on crack momentum"),
    ]

    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    years = sorted({d.year for d in p.index})
    say("=" * 96)
    say("PHASE 3 -- EXPANDING-WINDOW WALK-FORWARD")
    say(f"source {source}   cost {COST_BPS_ONE_WAY:.0f} bps one-way   "
        f"min train {MIN_TRAIN_YEARS}y")
    say("parameters re-selected before each year, on prior data only")
    say("=" * 96)

    summary = []
    for tag, struct, sig_col, label in CANDIDATES:
        if sig_col not in p.columns:
            say(f"\n[{tag}] skipped: {sig_col} not in panel")
            continue
        say("")
        say("-" * 96)
        say(f"[{tag}] {label}")
        say(f"   {'year':>6} {'look':>5} {'thr':>5} {'hold':>5} "
            f"{'trainSR':>8} {'oosNet%':>9} {'oosSR':>7} {'turn':>6} {'act%':>6}")
        pieces, chosen = [], []
        for y in years:
            if y - years[0] < MIN_TRAIN_YEARS:
                continue
            train = p.loc[: f"{y - 1}-12-31"]
            test = p.loc[f"{y}-01-01": f"{y}-12-31"]
            if len(test) < 60:
                continue
            sel = select(train, struct, sig_col)
            if sel is None:
                say(f"   {y:>6}   no eligible parameter set on train")
                continue
            lb, thr, h, tr_sr = sel
            # recompute on the full panel then slice, so rolling windows are
            # warm at the start of the test year (no artificial cold start)
            full = run(p, struct, sig_col, lb, thr, h)
            seg = full.loc[f"{y}-01-01": f"{y}-12-31"]
            s = stats(seg)
            pieces.append(seg)
            chosen.append((y, lb, thr, h))
            if "sharpe" in s:
                say(f"   {y:>6} {lb:>5} {thr:>5.2f} {h:>5} {tr_sr:>8.2f} "
                    f"{s['net_ann']:>9.2f} {s['sharpe']:>7.2f} "
                    f"{s['turnover_ann']:>6.1f} {s['days_in_mkt']:>6.1f}")
            else:
                say(f"   {y:>6} {lb:>5} {thr:>5.2f} {h:>5} {tr_sr:>8.2f}  (thin)")
        if not pieces:
            continue
        wf = pd.concat(pieces)
        s = stats(wf, label)
        say("")
        say(f"   WALK-FORWARD TOTAL ({wf.index.min().date()} .. {wf.index.max().date()}, "
            f"{len(wf)} days)")
        say(f"     net {s['net_ann']:+.2f}%/yr   gross {s['gross_ann']:+.2f}%   "
            f"cost {s['cost_ann']:.2f}%   vol {s['vol_ann']:.2f}%")
        say(f"     Sharpe {s['sharpe']:+.2f}   maxDD {s['max_dd']:.2f}%   "
            f"hit {s['hit']:.1f}%   t {s['t_stat']:+.2f}")
        yr = wf["net"].groupby(wf.index.year).sum() * 100
        say(f"     positive years {int((yr > 0).sum())}/{len(yr)}:  "
            + " ".join(f"{y}:{v:+.1f}" for y, v in yr.items()))
        # parameter stability: did the selection keep changing its mind?
        lbs = [c[1] for c in chosen]
        say(f"     selected lookback varied over {sorted(set(lbs))} "
            f"({len(set(lbs))} distinct values in {len(lbs)} years)")
        summary.append({"tag": tag, "label": label, **s,
                        "pos_years": int((yr > 0).sum()), "n_years": len(yr),
                        "param_churn": len(set(lbs))})
        wf["net"].cumsum().to_csv(OUT / f"phase3_wf_{tag}_{source}.csv")

    # ---------------- verdict ----------------
    say("")
    say("=" * 96)
    say("VERDICT")
    say("")
    if not summary:
        say("   nothing ran.")
    else:
        S = pd.DataFrame(summary)
        say(f"   {'':<3} {'structure':<42} {'net%':>7} {'SR':>6} {'maxDD%':>8} "
            f"{'t':>6} {'+yrs':>6}")
        for _, r in S.iterrows():
            say(f"   {r.tag:<3} {r.label:<42} {r.net_ann:>7.2f} {r.sharpe:>6.2f} "
                f"{r.max_dd:>8.2f} {r.t_stat:>6.2f} "
                f"{int(r.pos_years)}/{int(r.n_years):<4}")
        say("")
        best = S.sort_values("sharpe", ascending=False).iloc[0]
        say(f"   best structure: [{best.tag}] {best.label}")
        checks = {
            "walk-forward net > 0": best.net_ann > 0,
            "walk-forward Sharpe > 0.5": best.sharpe > 0.5,
            "walk-forward t > 2.0": best.t_stat > 2.0,
            "maxDD shallower than annual net": abs(best.max_dd) < max(best.net_ann, 1e-9),
            "positive in >=60% of years": best.pos_years / best.n_years >= 0.6,
        }
        for k, v in checks.items():
            say(f"   [{'PASS' if v else 'FAIL'}] {k}")
        n = int(sum(checks.values()))
        say("")
        say(f"   {n}/{len(checks)} checks passed.")
        say("")
        if n == len(checks):
            say("   -> DEPLOYABLE. Proceed to paper trading at small size.")
        elif n >= 4:
            say("   -> MARGINAL. Paper trade; do not commit capital yet.")
        else:
            say("   -> NOT DEPLOYABLE. No structure in this project earns capital.")
    say("=" * 96)

    (OUT / f"phase3_walkforward_{source}.txt").write_text("\n".join(report),
                                                          encoding="utf-8")
    print(f"\nwrote outputs/phase3_walkforward_{source}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
