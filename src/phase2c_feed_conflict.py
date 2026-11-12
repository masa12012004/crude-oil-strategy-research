"""Phase 2c: the feeds disagree. Which is it -- the sample, or the bar boundary?

Phase 2b gave Sharpe 0.24 on the yfinance crude feed (2010-2026) and 0.91 on the
MT5 feed (2021-2026, all it has). Two explanations:

  (a) SAMPLE. 2022-2026 was simply a good period for the trade, and yfinance
      restricted to the same window would look just as good. Then the strategy
      is period-dependent but the feeds agree, and the honest full-sample
      answer is the weak one.

  (b) BAR BOUNDARY. Phase 0 measured only 0.888 return correlation between the
      feeds because Exness cuts the daily bar at EET midnight while ICE/NYMEX
      cut elsewhere. If so the MT5 edge lives in that specific 03:30-IST cut --
      which, note, is the cut a live MT5 system would actually trade on, but
      which has only ~4 years of evidence behind it.

This script runs identical parameters on both feeds over the identical window.
No new parameters are fitted, so this consumes no further holdout credibility.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.strategy import backtest, build_legs, stats  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

# MT5's usable span (first bar 2021-10-27, so the 60d vol window warms up ~Jan 22)
COMMON = ("2022-01-01", "2026-11-06")
# the parameters Phase 2b selected on each feed
PARAMS = {"yf": dict(lookback=40, threshold=0.75, hold=1),
          "mt5": dict(lookback=3, threshold=0.5, hold=1)}


def load(src: str) -> pd.DataFrame:
    return build_legs(
        pd.read_csv(PROC / f"panel_{src}.csv", parse_dates=["date"]).set_index("date")
    )


def main() -> int:
    panels = {s: load(s) for s in ("yf", "mt5")}
    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    say("=" * 88)
    say("PHASE 2c -- FEED CONFLICT: same parameters, same window, both feeds")
    say(f"common window {COMMON[0]} .. {COMMON[1]}  (limited by MT5 history)")
    say("=" * 88)

    for pname, pp in PARAMS.items():
        say("")
        say(f"parameters selected on the '{pname}' feed: "
            f"lookback={pp['lookback']}d threshold={pp['threshold']} hold={pp['hold']}d")
        say(f"   {'feed':<6} {'net%':>7} {'gross%':>7} {'cost%':>6} {'vol%':>6} "
            f"{'Sharpe':>7} {'maxDD%':>7} {'hit%':>6} {'turn':>6} {'t':>6}")
        for src, p in panels.items():
            bt = backtest(p.loc[COMMON[0]:COMMON[1]], pp["threshold"], pp["hold"],
                          "overnight", lookback=pp["lookback"])
            s = stats(bt)
            if "sharpe" not in s:
                say(f"   {src:<6} insufficient sample")
                continue
            say(f"   {src:<6} {s['net_ann']:>7.2f} {s['gross_ann']:>7.2f} "
                f"{s['cost_ann']:>6.2f} {s['vol_ann']:>6.2f} {s['sharpe']:>7.2f} "
                f"{s['max_dd']:>7.2f} {s['hit']:>6.1f} {s['turnover_ann']:>6.1f} "
                f"{s['t_stat']:>6.2f}")

    # how different are the positions the two feeds generate?
    say("")
    say("-" * 88)
    say("POSITION AGREEMENT between feeds (mt5 params, common window)")
    pp = PARAMS["mt5"]
    pos = {}
    for src, p in panels.items():
        bt = backtest(p.loc[COMMON[0]:COMMON[1]], pp["threshold"], pp["hold"],
                      "overnight", lookback=pp["lookback"])
        pos[src] = bt["pos"]
    both = pd.DataFrame(pos).dropna()
    agree = float((both["yf"] == both["mt5"]).mean())
    corr = float(both["yf"].corr(both["mt5"]))
    say(f"   identical position on {100 * agree:.1f}% of days;  "
        f"position correlation {corr:.3f}")
    say("")
    say("-" * 88)
    say("ALSO: yfinance feed, FULL history, at the mt5-selected parameters")
    say("   (does the mt5 parameter choice work over 2010-2026 at all?)")
    bt = backtest(panels["yf"], pp["threshold"], pp["hold"], "overnight",
                  lookback=pp["lookback"])
    s = stats(bt)
    say(f"   2010-2026: net {s['net_ann']:.2f}%/yr  Sharpe {s['sharpe']:.2f}  "
        f"maxDD {s['max_dd']:.1f}%  t={s['t_stat']:.2f}")
    yr = bt["net"].groupby(bt.index.year).sum() * 100
    say(f"   positive years {int((yr > 0).sum())}/{len(yr)}")
    say("   " + "  ".join(f"{y}:{v:+.1f}" for y, v in yr.items()))
    say("=" * 88)

    (OUT / "phase2c_feed_conflict.txt").write_text("\n".join(report), encoding="utf-8")
    print("\nwrote outputs/phase2c_feed_conflict.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
