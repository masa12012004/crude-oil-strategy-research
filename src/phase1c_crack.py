"""Phase 1c: does the REFINING MARGIN predict Indian OMCs, where crude price did not?

Hypothesis, stated before measurement
-------------------------------------
Phase 1 found crude price has ~zero predictive content for OMCs, because crude
is only the first link in the chain and enters margins with the wrong sign plus
policy noise. The refining margin is the variable that actually drives OMC
profitability, so:

    crack spread up  ->  refining margin up  ->  OMCs outperform   [POSITIVE beta]

Note this is the OPPOSITE sign to the crude-price relationship, and it predicts
OMCs directly rather than the upstream-minus-OMC spread. If the margin story is
right, the OMC leg should come alive on a signal it was dead on before.

Two deliberate changes from Phase 1
-----------------------------------
1. HORIZONS. Phase 2 proved daily frequency cannot clear NSE costs. The margin
   -> earnings transmission is weekly-to-quarterly anyway, so horizons of
   1/5/21/63 days are measured and the longer ones are the ones that matter.
2. NO SINGLE HOLDOUT. 2024-2026 was spent by Phase 2's three looks. Validation
   moves to expanding-window walk-forward (phase3_walkforward.py), which has no
   reserved slice to burn.

Everything here is measurement. No parameters are chosen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import OMC, UPSTREAM, REGIMES  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

HORIZONS = [1, 5, 21, 63]
NAMES = list(OMC) + ["OMC"] + list(UPSTREAM) + ["UP"]


def ic(x: pd.Series, y: pd.Series, min_n: int = 60):
    m = x.notna() & y.notna()
    if m.sum() < min_n:
        return np.nan, np.nan, int(m.sum())
    r, p = stats.spearmanr(x[m], y[m])
    return float(r), float(p), int(m.sum())


def eff_t(r: float, n: int, h: int) -> float:
    """t-stat on an IC from OVERLAPPING h-day forward returns.

    Overlapping windows inflate the naive t by ~sqrt(h), which is how most
    multi-horizon studies accidentally find significance. Divide the effective
    sample by h before computing t.
    """
    if np.isnan(r) or n <= h + 2:
        return np.nan
    n_eff = n / h
    return float(r * np.sqrt(max(n_eff - 2, 1) / max(1 - r * r, 1e-9)))


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    OUT.mkdir(parents=True, exist_ok=True)
    p = pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")

    # baskets in return space
    p["OMC_ret"] = p[[f"{n}_ret" for n in OMC]].mean(axis=1)
    p["UP_ret"] = p[[f"{n}_ret" for n in UPSTREAM]].mean(axis=1)
    # forward returns at each horizon, entered at the open of day t (signal is
    # known 03:30 IST) and exited at the close of day t+h-1
    for n in NAMES:
        legs = (OMC if n == "OMC" else UPSTREAM if n == "UP" else [n])
        o = pd.concat([np.log(p[f"{x}_open"]) for x in legs], axis=1).mean(axis=1)
        c = pd.concat([np.log(p[f"{x}_close"]) for x in legs], axis=1).mean(axis=1)
        for h in HORIZONS:
            p[f"{n}_f{h}"] = c.shift(-(h - 1)) - o
    p["SPREAD_f"] = np.nan
    for h in HORIZONS:
        p[f"SPREAD_f{h}"] = 0.5 * (p[f"UP_f{h}"] - p[f"OMC_f{h}"])

    SIGS = {
        "crack321_chg": "crack 1d change",
        "crack321_chg5": "crack 5d change",
        "crack321_chg21": "crack 21d change",
        "crack321_z": "crack LEVEL z (252d)",
        "brent_ret": "brent 1d return (Phase 1 baseline)",
    }

    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    say("=" * 94)
    say(f"PHASE 1c -- REFINING MARGIN (3-2-1 CRACK) -> INDIAN OIL EQUITIES")
    say(f"source {source}   sample {p.index.min().date()} .. {p.index.max().date()}")
    say("hypothesis: crack up -> OMC margins up -> OMCs outperform (POSITIVE beta)")
    say("t-stats are corrected for overlapping windows (n_eff = n / horizon)")
    say("=" * 94)

    # ---------------- 1. IC by signal x horizon ----------------
    rows = []
    for sig, label in SIGS.items():
        if sig not in p.columns:
            continue
        say("")
        say(f"signal: {label}")
        say(f"   {'target':<10}" + "".join(
            f"{'IC@' + str(h) + 'd':>12}" for h in HORIZONS) + "   "
            + "".join(f"{'t@' + str(h):>8}" for h in HORIZONS))
        for n in NAMES + ["SPREAD"]:
            cells, tcells, rec = "", "", {"signal": label, "name": n}
            for h in HORIZONS:
                tgt = f"{n}_f{h}"
                if tgt not in p.columns:
                    cells += f"{'--':>12}"
                    tcells += f"{'--':>8}"
                    continue
                r, pv, nn = ic(p[sig], p[tgt])
                t = eff_t(r, nn, h)
                cells += f"{r:>12.4f}" if not np.isnan(r) else f"{'--':>12}"
                tcells += f"{t:>8.2f}" if not np.isnan(t) else f"{'--':>8}"
                rec[f"ic_{h}"] = r
                rec[f"t_{h}"] = t
            rows.append(rec)
            say(f"   {n:<10}{cells}   {tcells}")
    T = pd.DataFrame(rows)
    T.to_csv(OUT / f"phase1c_ic_{source}.csv", index=False)

    # ---------------- 2. regime stability of the best cell ----------------
    say("")
    say("-" * 94)
    say("2. REGIME STABILITY of the strongest |t| cell per signal")
    say("   (a signal that only works in one regime is not a signal)")
    for sig, label in SIGS.items():
        if sig not in p.columns:
            continue
        best, bt_ = None, 0.0
        for n in NAMES + ["SPREAD"]:
            for h in HORIZONS:
                tgt = f"{n}_f{h}"
                if tgt not in p.columns:
                    continue
                r, _, nn = ic(p[sig], p[tgt])
                t = eff_t(r, nn, h)
                if not np.isnan(t) and abs(t) > abs(bt_):
                    best, bt_ = (n, h, r), t
        if best is None:
            continue
        n, h, r = best
        say("")
        say(f"   {label}: best = {n} @ {h}d  (IC {r:+.4f}, t {bt_:+.2f})")
        signs = []
        for rn, (a, b) in REGIMES.items():
            sub = p.loc[a:b]
            rr, _, nn = ic(sub[sig], sub[f"{n}_f{h}"], min_n=40)
            if np.isnan(rr):
                say(f"     {rn:<14} --")
            else:
                signs.append(np.sign(rr))
                say(f"     {rn:<14} IC {rr:+.4f}   (n={nn})")
        if signs:
            ag = max(signs.count(1.0), signs.count(-1.0))
            say(f"     sign agreement {ag}/{len(signs)}")

    # ---------------- 3. is the crack signal independent of crude? ----------------
    say("")
    say("-" * 94)
    say("3. IS THE MARGIN SIGNAL NEW INFORMATION, OR REPACKAGED CRUDE?")
    say("   If crack signals correlate highly with crude returns, Phase 1c is")
    say("   just Phase 1 again and should be expected to fail the same way.")
    say("")
    cc = ["crack321_chg", "crack321_chg5", "crack321_chg21", "crack321_z",
          "brent_ret", "wti_ret"]
    cc = [c for c in cc if c in p.columns]
    say("   " + p[cc].corr().round(3).to_string().replace("\n", "\n   "))

    say("")
    say("=" * 94)
    say("4. READ-OUT")
    say("")
    # the decision-relevant summary
    cand = T.copy()
    tcols = [f"t_{h}" for h in HORIZONS if f"t_{h}" in cand.columns]
    cand["best_abs_t"] = cand[tcols].abs().max(axis=1)
    top = cand.sort_values("best_abs_t", ascending=False).head(8)
    say(f"   strongest cells overall (overlap-corrected |t|):")
    for _, r in top.iterrows():
        hh = max(HORIZONS, key=lambda h: abs(r.get(f"t_{h}", 0) or 0))
        say(f"     {r['name']:<8} {r['signal']:<36} @{hh:>3}d  "
            f"IC {r.get(f'ic_{hh}', float('nan')):+.4f}  t {r.get(f't_{hh}', float('nan')):+.2f}")
    say("")
    say("   A cell needs |t| > 2 AFTER overlap correction, plus regime sign")
    say("   agreement, before Phase 3 walk-forward is worth running on it.")
    say("=" * 94)

    (OUT / f"phase1c_report_{source}.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"\nwrote outputs/phase1c_report_{source}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
