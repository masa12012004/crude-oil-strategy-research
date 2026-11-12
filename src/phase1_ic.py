"""Phase 1: measurement only. No trading logic, no parameter search.

The single question: does crude, known BEFORE an executable NSE price, carry
predictive information about OMC returns -- and is the sign stable?

Outputs
  A  contemporaneous beta/corr      (LOOKAHEAD-CONTAMINATED -- sign diagnostic only)
  B  lead/lag IC scan               (where, if anywhere, the information sits)
  C  predictive IC by regime        (the gate number, two execution styles)
  D  rolling-250d sign stability    (is the beta usable or does it flip?)
  E  gate verdict

GATE: |IC| >= 0.03 AND the same sign in >= 4 of 5 regimes -> proceed to Phase 2.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import CRUDE, OMC, UPSTREAM, REGIMES  # noqa: E402

PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"

IC_MIN = 0.03
NAMES = list(OMC) + ["OMC"] + list(UPSTREAM)


def ic(x, y):
    """Spearman rank IC + p-value + n, on the overlapping non-null sample."""
    m = x.notna() & y.notna()
    if m.sum() < 60:
        return np.nan, np.nan, int(m.sum())
    r, p = stats.spearmanr(x[m], y[m])
    return float(r), float(p), int(m.sum())


def line(ch="-", n=78):
    return ch * n


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    if source not in ("mt5", "yf"):
        print("usage: phase1_ic.py [mt5|yf]", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    p = pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"])
    p = p.set_index("date", drop=False)

    # open-execution target: signal known at 03:30 IST -> trade the 09:15 open,
    # harvest open->close the same day. Freshest honest use of a crude daily bar.
    for n in NAMES:
        oc, cc = f"{n}_open", f"{n}_close"
        if oc in p.columns and cc in p.columns:
            p[f"{n}_o2c"] = np.log(p[cc] / p[oc])
    omc_o2c = [f"{n}_o2c" for n in OMC if f"{n}_o2c" in p.columns]
    p["OMC_o2c"] = p[omc_o2c].mean(axis=1)

    report = []

    def say(s=""):
        print(s)
        report.append(s)

    say(line("="))
    say(f"PHASE 1 -- CRUDE -> INDIAN OMC INFORMATION CONTENT   [crude source: {source}]")
    say(f"sample {p.date.min().date()} -> {p.date.max().date()}   {len(p)} NSE trading days")
    say(line("="))

    # ---------------- A. contaminated contemporaneous diagnostic ----------------
    say("")
    say("A. SAME-CALENDAR-DATE CORRELATION  (lookahead-contaminated; sign check only)")
    say("   naive date join: crude bar D vs NSE day D. crude bar D closes 03:30 IST")
    say("   on D+1, i.e. AFTER the 15:30 IST NSE close. NOT TRADABLE.")
    tag = CRUDE["brent"] if source == "mt5" else "YF"
    naive = pd.read_csv(RAW / f"crude_brent_{tag}_D1.csv",
                        parse_dates=["server_time"])
    naive = naive[naive["close"] > 0]
    naive["date"] = naive["server_time"].dt.normalize()
    naive["brent_naive_ret"] = np.log(naive["close"]).diff()
    nv = p[["date"] + [f"{n}_ret" for n in NAMES if f"{n}_ret" in p.columns]] \
        .reset_index(drop=True) \
        .merge(naive[["date", "brent_naive_ret"]], on="date", how="inner")
    say("")
    say(f"   {'name':<10} {'pearson':>9} {'beta':>9} {'spearman':>9} {'n':>7}")
    for n in NAMES:
        col = f"{n}_ret"
        if col not in nv.columns:
            continue
        m = nv[col].notna() & nv["brent_naive_ret"].notna()
        if m.sum() < 60:
            continue
        x, y = nv.loc[m, "brent_naive_ret"], nv.loc[m, col]
        pe = float(np.corrcoef(x, y)[0, 1])
        beta = float(np.polyfit(x, y, 1)[0])
        sp, _, nn = ic(x, y)
        say(f"   {n:<10} {pe:>9.3f} {beta:>9.3f} {sp:>9.3f} {nn:>7d}")

    # ---------------- B. lead/lag scan ----------------
    say("")
    say(line())
    say("B. LEAD/LAG SPEARMAN IC SCAN -- brent return vs OMC-basket return")
    say("   panel brent_ret at row t is already the bar t-1 return (lookahead-safe).")
    say("   k = extra NSE-day shift applied to the crude series.")
    say("")
    say(f"   {'shift k':>8} {'IC(OMC)':>10} {'p':>9} {'n':>7}")
    for k in range(-3, 6):
        r, pv, nn = ic(p["brent_ret"].shift(k), p["OMC_ret"])
        say(f"   {k:>8d} {r:>10.4f} {pv:>9.3f} {nn:>7d}")

    # ---------------- C. predictive IC by regime ----------------
    say("")
    say(line())
    say("C. PREDICTIVE IC BY REGIME  (signal strictly precedes the executable price)")
    say("   close-exec : brent bar t-1  ->  OMC close_t -> close_t+1")
    say("   open-exec  : brent bar t-1  ->  OMC open_t  -> close_t   (freshest)")

    signals = {
        "brent_ret": "brent 1d return",
        "brent_inr_ret": "brent-in-INR 1d return",
        "bw_spread_chg": "Brent-WTI spread change",
    }
    rows = []
    for sig, label in signals.items():
        if sig not in p.columns:
            continue
        for exec_style, tgt_suffix in (("close", "_fwd1"), ("open", "_o2c")):
            for n in NAMES:
                tgt = f"{n}{tgt_suffix}"
                if tgt not in p.columns:
                    continue
                full_r, full_p, full_n = ic(p[sig], p[tgt])
                rec = {"signal": label, "exec": exec_style, "name": n,
                       "IC_full": full_r, "p": full_p, "n": full_n}
                signs = []
                for rname, (s, e) in REGIMES.items():
                    sub = p.loc[s:e]
                    r, _, nn = ic(sub[sig], sub[tgt])
                    rec[rname] = r
                    if not np.isnan(r):
                        signs.append(np.sign(r))
                rec["sign_agree"] = (
                    int(max(signs.count(1.0), signs.count(-1.0))) if signs else 0
                )
                rec["n_regimes"] = len(signs)
                rows.append(rec)
    res = pd.DataFrame(rows)

    for sig_label in res.signal.unique():
        for exec_style in ("open", "close"):
            blk = res[(res.signal == sig_label) & (res["exec"] == exec_style)]
            if blk.empty:
                continue
            say("")
            say(f"   signal = {sig_label}   |   exec = {exec_style}")
            say(f"   {'name':<10} {'IC':>8} {'p':>7}"
                + "".join(f" {r[:9]:>10}" for r in REGIMES) + f" {'agree':>7}")
            for _, r in blk.iterrows():
                cells = "".join(
                    f" {r[k]:>10.3f}" if not np.isnan(r[k]) else f" {'--':>10}"
                    for k in REGIMES)
                say(f"   {r['name']:<10} {r.IC_full:>8.4f} {r.p:>7.3f}{cells}"
                    f"   {r.sign_agree}/{r.n_regimes}")

    res.to_csv(OUT / f"phase1_ic_table_{source}.csv", index=False)

    # ---------------- D. rolling sign stability ----------------
    say("")
    say(line())
    say("D. ROLLING 250d CORRELATION STABILITY  (brent bar t-1 vs OMC fwd1)")
    say("")
    say(f"   {'name':<10} {'mean':>8} {'std':>8} {'min':>8} {'max':>8} {'%neg':>7}")
    for n in NAMES:
        tgt = f"{n}_fwd1"
        if tgt not in p.columns:
            continue
        rc = p["brent_ret"].rolling(250).corr(p[tgt]).dropna()
        if rc.empty:
            continue
        say(f"   {n:<10} {rc.mean():>8.3f} {rc.std():>8.3f} {rc.min():>8.3f} "
            f"{rc.max():>8.3f} {100 * (rc < 0).mean():>6.1f}%")

    say("")
    say("   Same, but contemporaneous same-day beta (how stable is the ECONOMIC link)")
    say(f"   {'name':<10} {'mean':>8} {'std':>8} {'min':>8} {'max':>8} {'%neg':>7}")
    nvi = nv.set_index("date")
    for n in NAMES:
        col = f"{n}_ret"
        if col not in nvi.columns:
            continue
        rc = nvi["brent_naive_ret"].rolling(250).corr(nvi[col]).dropna()
        if rc.empty:
            continue
        say(f"   {n:<10} {rc.mean():>8.3f} {rc.std():>8.3f} {rc.min():>8.3f} "
            f"{rc.max():>8.3f} {100 * (rc < 0).mean():>6.1f}%")

    # intra-basket correlation: confirms the 3 names are one bet
    say("")
    say("   OMC pairwise daily return correlation (are these 3 independent bets?)")
    cm = p[[f"{n}_ret" for n in OMC]].corr()
    say("   " + cm.round(3).to_string().replace("\n", "\n   "))

    # ---------------- E. gate ----------------
    say("")
    say(line("="))
    say("E. PHASE 1 GATE")
    say(f"   criterion: |IC| >= {IC_MIN} AND sign agreement >= 4/5 regimes")
    passing = res[(res.IC_full.abs() >= IC_MIN) & (res.sign_agree >= 4)]
    say("")
    if passing.empty:
        say("   RESULT: FAIL -- no signal/target/exec combination clears the gate.")
        say("   Do NOT proceed to Phase 2 with this signal set.")
    else:
        say(f"   RESULT: {len(passing)} combination(s) clear the gate:")
        for _, r in passing.sort_values("IC_full", key=abs, ascending=False).iterrows():
            say(f"     {r['name']:<10} {r['exec']:<6} {r['signal']:<26} "
                f"IC={r.IC_full:+.4f} p={r.p:.4f} agree={r.sign_agree}/{r.n_regimes}")
    say(line("="))

    (OUT / f"phase1_report_{source}.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"\nwrote outputs/phase1_report_{source}.txt "
          f"and outputs/phase1_ic_table_{source}.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
