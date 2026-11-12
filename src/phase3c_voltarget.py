"""Phase 3c: fix structure B's one failing check -- the 42% drawdown.

Phase 3b established that structure B's crude signal is real: 8.54%/yr alpha
over its own upstream beta (t=2.03) and the 99.4th percentile against
random timing with an identical exposure profile (p=0.006). The single failing
check was risk: 21.5% vol and a 42% drawdown for a 13% return, i.e. a Sharpe
(0.61) barely above simply buying the Nifty (0.58).

That is a RISK problem, not a signal problem, and it has a standard fix that is
not a parameter search: scale the position by target_vol / realised_vol.

Pre-specified, ONE configuration, no grid, declared before running:
  - target annualised vol 15% (roughly Nifty's own 16%, so the comparison is fair)
  - realised vol from a 60-day trailing window of the UPSTREAM return (the
    traded asset), strictly backward-looking
  - leverage CAPPED AT 1.0 -- the overlay may only DE-risk, never gear up. This
    matters: uncapped vol-targeting adds leverage in calm markets, which flatters
    a backtest and is how this kind of overlay usually cheats.

Applied on top of the same expanding-window walk-forward, so every scaling
factor uses only prior data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.strategy import build_legs, stats, COST_BPS_ONE_WAY  # noqa: E402
from src.phase3_walkforward import run, select  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

TARGET_VOL = 0.15
VOL_WINDOW = 60
MAX_LEVERAGE = 1.0
WF_START = 2015


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    p = build_legs(
        pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")
    )
    # backward-looking realised vol of the traded asset, lagged one day so the
    # scaler is known before the position is taken
    rv = p["UP_o2o"].rolling(VOL_WINDOW).std().shift(1) * np.sqrt(252)
    scaler = (TARGET_VOL / rv).clip(upper=MAX_LEVERAGE)

    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    pieces_raw, pieces_vt = [], []
    for y in sorted({d.year for d in p.index}):
        if y < WF_START:
            continue
        train = p.loc[: f"{y - 1}-12-31"]
        if len(p.loc[f"{y}-01-01":f"{y}-12-31"]) < 60:
            continue
        sel = select(train, "UP", "brent_ret")
        if sel is None:
            continue
        lb, thr, h, _ = sel
        full = run(p, "UP", "brent_ret", lb, thr, h)
        seg = full.loc[f"{y}-01-01": f"{y}-12-31"]
        pieces_raw.append(seg)
        # re-derive the vol-targeted leg from scaled positions
        sp = (full["pos"] * scaler.reindex(full.index)).fillna(0.0)
        turn = sp.diff().abs().fillna(sp.abs())
        gross = sp * full["ret"]
        vt = pd.DataFrame({"pos": sp, "ret": full["ret"], "gross": gross,
                           "turnover": turn,
                           "cost": turn * COST_BPS_ONE_WAY / 1e4,
                           "net": gross - turn * COST_BPS_ONE_WAY / 1e4})
        pieces_vt.append(vt.loc[f"{y}-01-01": f"{y}-12-31"])

    raw = pd.concat(pieces_raw).dropna(subset=["ret"])
    vt = pd.concat(pieces_vt).dropna(subset=["ret"])
    a, b = raw.index.min(), raw.index.max()
    bh = p.loc[a:b, "UP_o2o"].dropna()
    nifty = p.loc[a:b, "NIFTY_ret"].dropna()

    say("=" * 92)
    say("PHASE 3c -- VOL-TARGETED STRUCTURE B (walk-forward)")
    say(f"target vol {TARGET_VOL:.0%}   vol window {VOL_WINDOW}d   "
        f"leverage cap {MAX_LEVERAGE:.1f} (de-risk only)")
    say(f"window {a.date()} .. {b.date()}   {len(raw)} days")
    say("=" * 92)

    def line(label: str, r: pd.Series, extra: str = "") -> None:
        ann = r.mean() * 252 * 100
        vol = r.std() * np.sqrt(252) * 100
        sr = ann / vol if vol else float("nan")
        eq = r.cumsum()
        dd = (eq - eq.cummax()).min() * 100
        calmar = ann / abs(dd) if dd else float("nan")
        say(f"   {label:<32} {ann:>8.2f} {vol:>7.2f} {sr:>7.2f} {dd:>9.2f} "
            f"{calmar:>8.2f} {extra}")

    say("")
    say(f"   {'':<32} {'net%/yr':>8} {'vol%':>7} {'Sharpe':>7} {'maxDD%':>9} "
        f"{'Calmar':>8}")
    line("B raw (Phase 3)", raw["net"])
    line("B vol-targeted (Phase 3c)", vt["net"])
    line("buy & hold upstream", bh)
    line("buy & hold Nifty", nifty)

    sv = stats(vt)
    sr_ = stats(raw)
    say("")
    say(f"   average scaler applied: {float(scaler.reindex(vt.index).mean()):.2f} "
        f"(1.00 = no de-risking); scaler capped on "
        f"{100 * float((scaler.reindex(vt.index) >= MAX_LEVERAGE).mean()):.0f}% of days")
    say(f"   turnover: raw {sr_['turnover_ann']:.1f}x/yr -> "
        f"vol-targeted {sv['turnover_ann']:.1f}x/yr   "
        f"cost {sr_['cost_ann']:.2f}% -> {sv['cost_ann']:.2f}%")

    yr = vt["net"].groupby(vt.index.year).sum() * 100
    say("")
    say(f"   calendar years ({int((yr > 0).sum())}/{len(yr)} positive):")
    say("   " + " ".join(f"{y}:{v:+.1f}" for y, v in yr.items()))

    say("")
    say("=" * 92)
    say("VERDICT -- the full check set, re-run on the vol-targeted version")
    say("")
    nifty_sr = (nifty.mean() * 252) / (nifty.std() * np.sqrt(252))
    checks = {
        "walk-forward net > 0": sv["net_ann"] > 0,
        "walk-forward Sharpe > 0.5": sv["sharpe"] > 0.5,
        "walk-forward t > 2.0": sv["t_stat"] > 2.0,
        "maxDD shallower than annual net": abs(sv["max_dd"]) < sv["net_ann"],
        "positive in >=60% of years": float((yr > 0).mean()) >= 0.6,
        "Sharpe beats buy&hold Nifty": sv["sharpe"] > nifty_sr,
    }
    for k, v in checks.items():
        say(f"   [{'PASS' if v else 'FAIL'}] {k}")
    n = int(sum(checks.values()))
    say("")
    say(f"   {n}/{len(checks)} checks passed.   "
        f"(Nifty Sharpe over this window: {nifty_sr:.2f})")
    say("")
    if n == len(checks):
        say("   -> DEPLOYABLE at small size, with the caveats in")
        say("      research/phase3_findings.md. Paper trade first.")
    elif n >= 4:
        say("   -> MARGINAL but real. Paper trade; size small if at all.")
    else:
        say("   -> NOT DEPLOYABLE.")
    say("=" * 92)

    (OUT / f"phase3c_voltarget_{source}.txt").write_text("\n".join(report),
                                                         encoding="utf-8")
    vt["net"].cumsum().to_csv(OUT / f"phase3c_equity_{source}.csv")
    print(f"\nwrote outputs/phase3c_voltarget_{source}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
