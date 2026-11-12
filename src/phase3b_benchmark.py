"""Phase 3b: is structure B a signal, or just long upstream beta?

Phase 3 walk-forward gave structure B (long/flat upstream on brent momentum)
+13.12%/yr net, Sharpe 0.61, t=2.08 over 12 honest out-of-sample years. But B is
LONG-ONLY and in the market 47-91% of the time. If simply holding ONGC+OIL over
the same window returned as much, the crude signal contributed nothing and the
whole project has produced an expensive way to be long two oil stocks.

This is the test that decides whether anything here is real:

  1. buy-and-hold upstream over the identical window
  2. B's return vs that, and B's alpha after regressing out upstream beta
  3. a random-timing control with B's exact time-in-market, bootstrapped,
     to see where B's return sits in the distribution of luck
  4. Nifty, as the opportunity cost of any Indian equity exposure
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.strategy import build_legs, stats, COST_BPS_ONE_WAY  # noqa: E402
from src.phase3_walkforward import (LOOKBACKS, THRESHOLDS, HOLDS,  # noqa: E402
                                    MIN_ACTIVE, MIN_TRAIN_YEARS, run, select)

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
WF_START = 2015
N_BOOT = 2000
RNG = np.random.default_rng(20261109)


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    p = build_legs(
        pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")
    )
    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    # rebuild structure B's walk-forward exactly as Phase 3 did
    pieces = []
    for y in sorted({d.year for d in p.index}):
        if y < WF_START:
            continue
        train = p.loc[: f"{y - 1}-12-31"]
        test = p.loc[f"{y}-01-01": f"{y}-12-31"]
        if len(test) < 60:
            continue
        sel = select(train, "UP", "brent_ret")
        if sel is None:
            continue
        lb, thr, h, _ = sel
        pieces.append(run(p, "UP", "brent_ret", lb, thr, h)
                      .loc[f"{y}-01-01": f"{y}-12-31"])
    wf = pd.concat(pieces)
    a, b = wf.index.min(), wf.index.max()

    say("=" * 90)
    say("PHASE 3b -- IS STRUCTURE B A SIGNAL OR JUST UPSTREAM BETA?")
    say(f"window {a.date()} .. {b.date()}   {len(wf)} days   source {source}")
    say("=" * 90)

    bh = p.loc[a:b, "UP_o2o"].dropna()          # buy and hold upstream
    nifty = p.loc[a:b, "NIFTY_ret"].dropna()    # Indian equity benchmark
    sB = stats(wf)
    tim = float((wf["pos"] != 0).mean())
    avg_exp = float(wf["pos"].abs().mean())

    def line(label: str, r: pd.Series, extra: str = "") -> None:
        ann = r.mean() * 252 * 100
        vol = r.std() * np.sqrt(252) * 100
        sr = ann / vol if vol else float("nan")
        eq = r.cumsum()
        dd = (eq - eq.cummax()).min() * 100
        say(f"   {label:<34} {ann:>8.2f} {vol:>8.2f} {sr:>7.2f} {dd:>9.2f} {extra}")

    say("")
    say("1. HEAD TO HEAD")
    say("")
    say(f"   {'':<34} {'net%/yr':>8} {'vol%':>8} {'Sharpe':>7} {'maxDD%':>9}")
    line("structure B (walk-forward)", wf["net"],
         f"  time in mkt {100 * tim:.0f}%, avg exposure {avg_exp:.2f}")
    line("buy & hold upstream (ONGC+OIL)", bh, "  always on, exposure 1.00")
    line("buy & hold Nifty", nifty)
    line("B, exposure-scaled to buy&hold", wf["net"] / max(avg_exp, 1e-9),
         "  B's return per unit of exposure")

    say("")
    say("-" * 90)
    say("2. ALPHA vs UPSTREAM BETA  (OLS: B_net ~ alpha + beta * upstream)")
    j = pd.DataFrame({"B": wf["net"], "UP": p.loc[a:b, "UP_o2o"]}).dropna()
    X = np.column_stack([np.ones(len(j)), j["UP"].values])
    coef, *_ = np.linalg.lstsq(X, j["B"].values, rcond=None)
    resid = j["B"].values - X @ coef
    se = np.sqrt(np.sum(resid ** 2) / (len(j) - 2)
                 * np.linalg.inv(X.T @ X)[0, 0])
    alpha_ann = coef[0] * 252 * 100
    say("")
    say(f"   beta to upstream      {coef[1]:>8.3f}")
    say(f"   alpha                 {alpha_ann:>8.2f} %/yr")
    say(f"   alpha t-stat          {coef[0] / se:>8.2f}")
    say("")
    say("   Beta near B's average exposure with alpha ~0 means the signal is")
    say("   doing nothing but choosing when to be long. Alpha is the only part")
    say("   that is actually the crude signal's contribution.")

    say("")
    say("-" * 90)
    say(f"3. RANDOM-TIMING CONTROL  ({N_BOOT} draws)")
    say("   Shuffle B's position series in blocks, keeping its exact exposure")
    say("   profile, and re-run against the same upstream returns. If B's actual")
    say("   return sits mid-distribution, the timing added nothing.")
    ret = p.loc[a:b, "UP_o2o"].reindex(wf.index).values
    pos = wf["pos"].values
    block = 21
    nb = int(np.ceil(len(pos) / block))
    draws = np.empty(N_BOOT)
    for i in range(N_BOOT):
        blocks = pos[: nb * block].reshape(-1, block) if len(pos) >= nb * block \
            else np.resize(pos, nb * block).reshape(-1, block)
        shuf = blocks[RNG.permutation(len(blocks))].ravel()[: len(pos)]
        g = np.nansum(shuf * ret)
        turn = np.abs(np.diff(shuf, prepend=0.0)).sum()
        draws[i] = (g - turn * COST_BPS_ONE_WAY / 1e4) / len(pos) * 252 * 100
    actual = sB["net_ann"]
    pct = float((draws < actual).mean())
    say("")
    say(f"   random-timing mean {draws.mean():+.2f}%/yr, "
        f"5th pct {np.percentile(draws, 5):+.2f}, 95th pct {np.percentile(draws, 95):+.2f}")
    say(f"   structure B actual {actual:+.2f}%/yr  ->  {100 * pct:.1f}th percentile")
    say(f"   empirical p-value (one-sided) = {1 - pct:.3f}")

    say("")
    say("=" * 90)
    say("VERDICT")
    say("")
    bh_s = bh.mean() * 252 * 100
    bh_sr = (bh.mean() * 252) / (bh.std() * np.sqrt(252))
    checks = {
        "B beats buy&hold upstream on return": sB["net_ann"] > bh_s,
        "B beats buy&hold upstream on Sharpe": sB["sharpe"] > bh_sr,
        "alpha vs upstream beta > 0": alpha_ann > 0,
        "alpha t-stat > 2": coef[0] / se > 2,
        "beats random timing at p<0.05": (1 - pct) < 0.05,
    }
    for k, v in checks.items():
        say(f"   [{'PASS' if v else 'FAIL'}] {k}")
    n = int(sum(checks.values()))
    say("")
    say(f"   {n}/{len(checks)} checks passed.")
    say("")
    if n >= 4:
        say("   -> The crude signal adds genuine value beyond holding upstream.")
    elif n >= 2:
        say("   -> PARTIAL. Some timing value, but most of the return is beta.")
    else:
        say("   -> The signal adds NOTHING. Structure B is long upstream with extra")
        say("      steps: same exposure, worse drawdown control, and trading cost")
        say("      on top. Holding ONGC+OIL outright would have done as well.")
    say("=" * 90)

    (OUT / f"phase3b_benchmark_{source}.txt").write_text("\n".join(report),
                                                         encoding="utf-8")
    print(f"\nwrote outputs/phase3b_benchmark_{source}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
