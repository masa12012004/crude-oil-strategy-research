"""Phase 4: per-stock volatility vs crude, and DIRECTION of response to crude.

Usage:  python src/phase4_direction.py [mt5|yf]      (default: yf)

Two distinct questions are kept strictly apart, because conflating them is the
single easiest way to fake an edge in this dataset:

  CONTEMPORANEOUS  crude bar dated D  vs  NSE day D
      Descriptive co-movement. Crude's D bar closes ~03:30 IST on D+1, i.e.
      AFTER the NSE close on D, so this is NOT tradable. It answers "do these
      move together, and in which direction" -- a risk/structure question.

  LAGGED (tradable)  crude bar dated D-1  vs  NSE day D
      The panel's own lookahead-safe alignment. This is the only version an
      actual trader could act on. Phase 1 already showed it is ~0 for OMCs;
      it is reported here again so the two columns sit next to each other and
      nobody can quote the contemporaneous number as if it were a signal.

Direction is measured three ways rather than one, because beta alone hides the
asymmetry that matters for a hedge:
  * beta / corr                 -- average linear direction
  * up-day vs down-day response -- is the reaction symmetric?
  * sign agreement rate         -- how often does it even move the same way?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import REGIMES  # noqa: E402

PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"

ANN = np.sqrt(252)
WIN = 60

ASSETS = [
    ("IOC", "IOC", "omc"),
    ("HINDPETRO", "HPCL", "omc"),
    ("BPCL", "BPCL", "omc"),
    ("ONGC", "ONGC", "upstream"),
    ("OIL", "Oil India", "upstream"),
    ("NIFTY", "Nifty 50", "index"),
]


def contemporaneous_brent(source, dates):
    """Crude return of the bar dated the SAME day as the NSE session."""
    tag = "UKOIL" if source == "mt5" else "YF"
    df = pd.read_csv(RAW / ("crude_brent_%s_D1.csv" % tag), parse_dates=["server_time"])
    df["bar_date"] = df["server_time"].dt.normalize()
    df = df.groupby("bar_date", as_index=False).last().sort_values("bar_date")
    df["ret"] = np.log(df["close"].where(df["close"] > 0)).diff()
    s = df.set_index("bar_date")["ret"]
    # exact same-date match only; NSE days with no crude bar stay NaN
    return s.reindex(dates)


def tstat(a, b):
    """Welch t for difference of two independent means."""
    a, b = a.dropna(), b.dropna()
    if len(a) < 20 or len(b) < 20:
        return np.nan
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else np.nan


def ols_beta(y, x):
    """beta and its t-stat, pairwise-complete."""
    d = pd.concat([y, x], axis=1).dropna()
    if len(d) < 30:
        return np.nan, np.nan
    yy, xx = d.iloc[:, 0].values, d.iloc[:, 1].values
    xm = xx - xx.mean()
    sxx = (xm ** 2).sum()
    if sxx <= 0:
        return np.nan, np.nan
    beta = float((xm * (yy - yy.mean())).sum() / sxx)
    resid = yy - yy.mean() - beta * xm
    s2 = (resid ** 2).sum() / (len(d) - 2)
    se = np.sqrt(s2 / sxx)
    return beta, (float(beta / se) if se > 0 else np.nan)


def describe(r, c, lagged):
    """All direction/vol stats for one asset against contemporaneous crude c."""
    d = pd.concat({"r": r, "c": c}, axis=1).dropna()
    up = d.loc[d["c"] > 0, "r"]
    dn = d.loc[d["c"] < 0, "r"]
    b_up, _ = ols_beta(d.loc[d["c"] > 0, "r"], d.loc[d["c"] > 0, "c"])
    b_dn, _ = ols_beta(d.loc[d["c"] < 0, "r"], d.loc[d["c"] < 0, "c"])
    beta, bt = ols_beta(d["r"], d["c"])
    beta_l, bt_l = ols_beta(r, lagged)
    return {
        "n": len(d),
        "vol": float(r.std() * ANN * 100),
        "vol_ratio": float(r.std() / c.std()) if c.std() > 0 else np.nan,
        "corr": float(d["r"].corr(d["c"])),
        "beta": beta,
        "beta_t": bt,
        "corr_lag": float(r.corr(lagged)),
        "beta_lag": beta_l,
        "beta_lag_t": bt_l,
        "up_mean": float(up.mean() * 100),
        "dn_mean": float(dn.mean() * 100),
        "ud_spread": float((up.mean() - dn.mean()) * 100),
        "ud_t": tstat(up, dn),
        "beta_up": b_up,
        "beta_dn": b_dn,
        "sign_agree": float((np.sign(d["r"]) == np.sign(d["c"])).mean() * 100),
    }


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    p = pd.read_csv(PROC / ("panel_%s.csv" % source), parse_dates=["date"]).set_index("date")
    cont = contemporaneous_brent(source, p.index)
    lag = p["brent_ret"]
    OUT.mkdir(parents=True, exist_ok=True)

    print("crude source: %s   NSE days %d   contemporaneous crude bars matched %d (%.1f%%)"
          % (source, len(p), int(cont.notna().sum()), 100 * cont.notna().mean()))
    print("sanity: corr(contemporaneous, lagged) = %+.3f  (must be ~0 -- different days)"
          % cont.corr(lag))
    bvol = float(cont.std() * ANN * 100)
    print("Brent own vol %.1f%%/yr\n" % bvol)

    rows = {}
    for key, label, grp in ASSETS:
        rows[label] = describe(p[key + "_ret"], cont, lag)
    T = pd.DataFrame(rows).T

    print("=" * 104)
    print("FULL SAMPLE  --  volatility and direction vs Brent")
    print("=" * 104)
    print("%-10s%7s%9s%8s%8s%7s%11s%10s%7s%10s"
          % ("asset", "vol%", "x Brent", "corr", "beta", "t",
             "| corr_lag", "beta_lag", "t", "| agree%"))
    for lb in T.index:
        r = T.loc[lb]
        print("%-10s%7.1f%9.2f%8.3f%8.3f%7.1f%11.3f%10.3f%7.1f%10.1f"
              % (lb, r["vol"], r["vol_ratio"], r["corr"], r["beta"], r["beta_t"],
                 r["corr_lag"], r["beta_lag"], r["beta_lag_t"], r["sign_agree"]))

    print("\n" + "=" * 104)
    print("DIRECTIONAL ASYMMETRY  --  response on crude-up vs crude-down days (contemporaneous)")
    print("=" * 104)
    print("%-10s%10s%10s%9s%7s%10s%10s%8s"
          % ("asset", "up-day %", "dn-day %", "spread", "t", "beta|up", "beta|dn", "asym"))
    for lb in T.index:
        r = T.loc[lb]
        print("%-10s%10.3f%10.3f%9.3f%7.2f%10.3f%10.3f%8.3f"
              % (lb, r["up_mean"], r["dn_mean"], r["ud_spread"], r["ud_t"],
                 r["beta_up"], r["beta_dn"], r["beta_up"] - r["beta_dn"]))

    print("\n" + "=" * 104)
    print("REGIME STABILITY  --  contemporaneous beta to Brent")
    print("=" * 104)
    reg = {}
    print("%-10s" % "asset" + "".join("%14s" % k for k in REGIMES))
    for key, label, grp in ASSETS:
        line, cells = "%-10s" % label, {}
        for rname, (lo, hi) in REGIMES.items():
            m = (p.index >= lo) & (p.index <= hi)
            b, t = ols_beta(p.loc[m, key + "_ret"], cont[m])
            cells[rname] = {"beta": b, "t": t}
            line += ("%9.3f(%3.1f)" % (b, t)) if np.isfinite(b) else "%14s" % "n/a"
        reg[label] = cells
        print(line)
    print("\n(beta with t-stat in brackets; sign flips across regimes are the story)")

    T.round(4).to_csv(OUT / ("phase4_direction_%s.csv" % source))

    # ---- WHERE in the day does the crude response happen? -------------------
    # The crude bar dated t-1 closes ~03:30 IST on day t: after the NSE close on
    # t-1, before the NSE open on t. So it can only be acted on at the open of t.
    # Splitting the stock's day into the overnight gap and the intraday session
    # tells us whether the response is already in the opening print (not
    # capturable by anyone who was flat overnight) or still available intraday.
    print("\n" + "=" * 104)
    print("WHERE THE RESPONSE LANDS  --  regressed on the crude bar that closed before the NSE open")
    print("=" * 104)
    print("%-10s%20s%20s%22s%10s"
          % ("asset", "full close-to-close", "gap c[t-1]->o[t]", "intraday o[t]->c[t]", "gap share"))
    print("%-10s%11s%9s%11s%9s%13s%9s%10s"
          % ("", "beta", "t", "beta", "t", "beta", "t", ""))
    gap_out = {}
    for key, label, grp in ASSETS:
        o, c = p[key + "_open"], p[key + "_close"]
        full = np.log(c.where(c > 0)).diff()
        gap = np.log(o.where(o > 0)) - np.log(c.where(c > 0).shift(1))
        intra = np.log(c.where(c > 0)) - np.log(o.where(o > 0))
        bf, tf = ols_beta(full, lag)
        bg, tg = ols_beta(gap, lag)
        bi, ti = ols_beta(intra, lag)
        share = 100 * bg / bf if bf not in (0, np.nan) and np.isfinite(bf) else np.nan
        gap_out[label] = {"beta_full": bf, "t_full": tf, "beta_gap": bg, "t_gap": tg,
                          "beta_intra": bi, "t_intra": ti, "gap_share": share}
        print("%-10s%11.3f%9.2f%11.3f%9.2f%13.3f%9.2f%9.0f%%"
              % (label, bf, tf, bg, tg, bi, ti, share))
    print("\n(a high gap share means the move is already in the opening print)")

    # rolling series for the visualisation.
    # MIN_P matters: `cont` is NaN on the ~4% of NSE days with no same-dated
    # crude bar, and a single NaN voids an entire 60-day window. Without
    # min_periods the rolling beta is NaN on 195 of 200 month-ends.
    MIN_P = 40
    roll = {}
    cvar = cont.rolling(WIN, min_periods=MIN_P).var()
    for key, label, grp in ASSETS:
        r = p[key + "_ret"]
        roll[label] = {
            "vol": r.rolling(WIN, min_periods=MIN_P).std() * ANN * 100,
            "corr": r.rolling(WIN, min_periods=MIN_P).corr(cont),
            "beta": r.rolling(WIN, min_periods=MIN_P).cov(cont) / cvar,
        }
    keep = roll["IOC"]["beta"].dropna().index
    idx = pd.Series(keep, index=keep).resample("ME").last().dropna()
    dates = pd.DatetimeIndex(idx.values)
    bvol_s = cont.rolling(WIN, min_periods=MIN_P).std() * ANN * 100

    def ser(d, nd):
        return [None if not np.isfinite(x) else round(float(x), nd) for x in d]

    payload = {
        "window": WIN, "source": source,
        "dates": [d.strftime("%Y-%m") for d in dates],
        "brent_vol": ser(bvol_s.loc[dates], 2),
        "assets": [{"key": l, "group": g} for _, l, g in ASSETS],
        "vol": {l: ser(roll[l]["vol"].loc[dates], 2) for _, l, _ in ASSETS},
        "corr": {l: ser(roll[l]["corr"].loc[dates], 3) for _, l, _ in ASSETS},
        "beta": {l: ser(roll[l]["beta"].loc[dates], 3) for _, l, _ in ASSETS},
        "stats": {l: {k: (None if not np.isfinite(float(v)) else round(float(v), 4))
                      for k, v in T.loc[l].items()} for _, l, _ in ASSETS},
        "regimes": {l: {r: {k: (None if v is None or not np.isfinite(v) else round(float(v), 3))
                            for k, v in c.items()} for r, c in cs.items()}
                    for l, cs in reg.items()},
        "brent_vol_full": round(bvol, 1),
        "gap": {l: {k: (None if not np.isfinite(v) else round(float(v), 3))
                    for k, v in c.items()} for l, c in gap_out.items()},
    }
    f = OUT / ("phase4_viz_%s.json" % source)
    f.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print("\n-> %s" % (OUT / ("phase4_direction_%s.csv" % source)))
    print("-> %s (%.0f KB, %d months)" % (f, f.stat().st_size / 1024, len(dates)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
