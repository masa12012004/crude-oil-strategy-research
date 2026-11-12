"""Phase 1b: the relative-value variant Phase 1 section C points to.

Phase 1 finding: upstream (ONGC/OIL) carries a STABLE POSITIVE crude beta while
the OMCs carry a WEAK NEGATIVE one. The common factor (Nifty / PSU / risk-on)
sits in both legs with the same sign, so it should cancel in the long-short
spread while the crude-driven component adds.

This measures whether the spread's crude IC actually exceeds either leg's.

CAUTION: the pair here was chosen by looking at the Phase 1 table, so this is a
HYPOTHESIS for Phase 2 to test out-of-sample, NOT an independent result. It is
reported with that label on it deliberately.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import OMC, REGIMES  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"


def ic(x, y):
    m = x.notna() & y.notna()
    if m.sum() < 60:
        return np.nan, np.nan, int(m.sum())
    r, p = stats.spearmanr(x[m], y[m])
    return float(r), float(p), int(m.sum())


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    p = pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")

    for n in list(OMC) + ["ONGC", "OIL"]:
        p[f"{n}_o2c"] = np.log(p[f"{n}_close"] / p[f"{n}_open"])
    p["OMC_o2c"] = p[[f"{n}_o2c" for n in OMC]].mean(axis=1)
    p["UP_o2c"] = p[["ONGC_o2c", "OIL_o2c"]].mean(axis=1)

    legs = {
        "UP (long upstream)": p["UP_o2c"],
        "OMC (long OMC)": p["OMC_o2c"],
        "UP - OMC spread": p["UP_o2c"] - p["OMC_o2c"],
        "ONGC - HINDPETRO": p["ONGC_o2c"] - p["HINDPETRO_o2c"],
    }

    report = []

    def say(s=""):
        print(s)
        report.append(s)

    say("=" * 78)
    say(f"PHASE 1b -- RELATIVE VALUE (HYPOTHESIS, NOT AN INDEPENDENT RESULT)")
    say(f"crude source: {source}   signal: brent bar t-1 return   exec: open_t -> close_t")
    say("=" * 78)
    say("")
    say(f"   {'leg':<20} {'IC':>8} {'p':>7}"
        + "".join(f" {r[:9]:>10}" for r in REGIMES) + "   agree")
    for label, series in legs.items():
        r, pv, nn = ic(p["brent_ret"], series)
        signs, cells = [], ""
        for rn, (s, e) in REGIMES.items():
            sub = p.loc[s:e]
            rr, _, _ = ic(sub["brent_ret"], series.loc[s:e])
            cells += f" {rr:>10.3f}" if not np.isnan(rr) else f" {'--':>10}"
            if not np.isnan(rr):
                signs.append(np.sign(rr))
        agree = max(signs.count(1.0), signs.count(-1.0)) if signs else 0
        say(f"   {label:<20} {r:>8.4f} {pv:>7.3f}{cells}   {agree}/{len(signs)}")

    # economic sizing: does any of this survive costs?
    say("")
    say("-" * 78)
    say("COST REALITY CHECK (open-exec, daily turnover)")
    say("   expected edge per trade ~= IC x sigma(target).  NSE round-trip cost on")
    say("   these names ~= 15-25 bps (brokerage + STT + exchange + impact).")
    say("")
    say(f"   {'leg':<20} {'IC':>8} {'sigma/day':>10} {'edge bps':>9} {'vs 20bps':>10}")
    for label, series in legs.items():
        r, _, _ = ic(p["brent_ret"], series)
        sd = float(series.std())
        edge = abs(r) * sd * 1e4
        say(f"   {label:<20} {r:>8.4f} {100 * sd:>9.2f}% {edge:>9.1f} "
            f"{'CLEARS' if edge > 20 else 'does not clear':>10}")
    say("")
    say("   Daily turnover is therefore not viable on any leg. If Phase 2 proceeds")
    say("   it must do so with threshold entries and multi-day holds, so that the")
    say("   per-trade edge is drawn from a larger move while cost is paid once.")
    say("=" * 78)

    (OUT / f"phase1b_spread_{source}.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"\nwrote outputs/phase1b_spread_{source}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
