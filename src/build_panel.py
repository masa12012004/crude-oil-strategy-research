"""Phase 0: build the lookahead-safe aligned daily panel -> data/processed/panel_<src>.csv

Usage:  python src/build_panel.py [mt5|yf]      (default: yf)

TWO CRUDE SOURCES, DELIBERATELY KEPT SEPARATE
---------------------------------------------
  mt5 : Exness UKOIL/USOIL CFD, daily bar = 00:00-24:00 broker server time
        (EET/EEST). This is what the live system will trade off. Only ~1,300
        bars retained (2021-10-27 ->), too short for the regime test.
  yf  : ICE Brent BZ=F / NYMEX WTI CL=F front-month, 2010 ->. Long enough for
        the regime test, but the bar is cut at a different hour of the day.

validate_crude.py shows close levels correlate 0.996 across the two but daily
RETURNS only ~0.89 (brent) / ~0.81 (wti) -- the differing bar boundary changes
the return series materially. They are therefore NOT interchangeable, and Phase 1
is run on each independently. A conclusion that holds on only one source is a
property of that feed's bar boundary, not of the market.

ALIGNMENT RULE (the single most important line in this project)
--------------------------------------------------------------
MT5 daily bar dated D spans D 00:00 -> D+1 00:00 broker server time (EET/EEST,
UTC+2/+3). It therefore CLOSES at ~03:30 IST on day D+1.

NSE cash day t closes 15:30 IST on day t.

So at the moment of the NSE close on day t, the newest *fully closed* crude bar
is the one dated t-1. Matching crude bar t to NSE day t -- the obvious thing to
do, and what a naive date-string join gives you -- reads 12 hours into the
future and will manufacture an edge that does not exist.

Implementation: crude bar D is stamped with avail_date = D + 1 day, then
merge_asof(backward) onto the NSE calendar. The NSE trading calendar is the
spine; crude is forward-filled onto it (never backfilled).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import CRUDE, OMC, UPSTREAM, MACRO  # noqa: E402

RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"


def load_crude(name: str, symbol: str, source: str) -> pd.DataFrame:
    tag = symbol if source == "mt5" else "YF"
    df = pd.read_csv(RAW / f"crude_{name}_{tag}_D1.csv", parse_dates=["server_time"])
    df["bar_date"] = df["server_time"].dt.normalize()
    df = df.groupby("bar_date", as_index=False).last()
    # April 2020: NYMEX WTI front-month settled NEGATIVE (-37.63 on 2020-04-20).
    # Log returns are undefined there and the move is a contract-expiry artefact,
    # not a crude price signal. Mask the affected window rather than silently
    # producing NaN/inf that would propagate into every IC in the report.
    bad = df["close"] <= 0
    if bad.any():
        lo, hi = df.loc[bad, "bar_date"].min(), df.loc[bad, "bar_date"].max()
        window = (df["bar_date"] >= lo - pd.Timedelta(days=5)) & \
                 (df["bar_date"] <= hi + pd.Timedelta(days=5))
        print(f"  {name}: {int(bad.sum())} non-positive closes "
              f"({lo.date()}..{hi.date()}); masking {int(window.sum())}-bar window")
        df.loc[window, ["open", "high", "low", "close"]] = np.nan
    # the bar is only known to an NSE trader on the NEXT calendar day
    df["avail_date"] = df["bar_date"] + pd.Timedelta(days=1)
    out = df[["avail_date", "bar_date", "open", "high", "low", "close", "tick_volume"]].copy()
    return out.rename(columns={
        "bar_date": f"{name}_bar_date",
        "open": f"{name}_open", "high": f"{name}_high",
        "low": f"{name}_low", "close": f"{name}_close",
        "tick_volume": f"{name}_vol",
    }).sort_values("avail_date").reset_index(drop=True)


def load_equity(group: str, name: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"{group}_{name}_D1.csv", parse_dates=["date"])
    df["date"] = df["date"].dt.tz_localize(None).dt.normalize()
    cols = {"Close": f"{name}_close", "Open": f"{name}_open",
            "High": f"{name}_high", "Low": f"{name}_low", "Volume": f"{name}_vol"}
    keep = ["date"] + [c for c in cols if c in df.columns]
    return df[keep].rename(columns=cols).sort_values("date").reset_index(drop=True)


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    if source not in ("mt5", "yf"):
        print("usage: build_panel.py [mt5|yf]", file=sys.stderr)
        return 2
    print(f"crude source: {source}")
    PROC.mkdir(parents=True, exist_ok=True)

    # --- spine: the NSE trading calendar, taken from the OMC with the most days ---
    eq = {}
    for group, mapping in (("omc", OMC), ("upstream", UPSTREAM), ("macro", MACRO)):
        for name in mapping:
            try:
                eq[name] = load_equity(group, name)
            except FileNotFoundError:
                print(f"skip {group}/{name}: raw file missing", file=sys.stderr)

    spine_src = max((n for n in OMC if n in eq), key=lambda n: len(eq[n]))
    panel = eq[spine_src][["date"]].copy()
    print(f"NSE spine from {spine_src}: {len(panel)} trading days "
          f"{panel.date.min().date()} -> {panel.date.max().date()}")

    for name, df in eq.items():
        panel = panel.merge(df, on="date", how="left")

    # --- crude, lookahead-safe ---
    for name, symbol in CRUDE.items():
        c = load_crude(name, symbol, source)
        panel = pd.merge_asof(panel, c, left_on="date", right_on="avail_date",
                              direction="backward")
        panel["_stale"] = (panel["date"] - panel[f"{name}_bar_date"]).dt.days
        n_stale = int((panel["_stale"] > 4).sum())
        print(f"{name:6s} {symbol:6s} merged; median bar age "
              f"{panel['_stale'].median():.0f}d, {n_stale} days with age>4 (holidays)")
        panel = panel.drop(columns=["avail_date", "_stale"])

    # --- refined products, same lookahead-safe rule as crude (Phase 1c) ---
    # These settle on the US session of day D, i.e. after the NSE close on D,
    # so avail_date = bar_date + 1 exactly as for crude.
    for prod in ("rbob", "heatoil", "natgas"):
        f = RAW / f"product_{prod}_D1.csv"
        if not f.exists():
            print(f"skip {prod}: raw file missing", file=sys.stderr)
            continue
        d = pd.read_csv(f, parse_dates=["server_time"])
        d["bar_date"] = d["server_time"].dt.normalize()
        d = d.groupby("bar_date", as_index=False).last()
        d["avail_date"] = d["bar_date"] + pd.Timedelta(days=1)
        d = d[["avail_date", "close"]].rename(columns={"close": f"{prod}_close"})
        panel = pd.merge_asof(panel, d.sort_values("avail_date"),
                              left_on="date", right_on="avail_date",
                              direction="backward").drop(columns=["avail_date"])

    # 3-2-1 crack spread in $/bbl: (2*RBOB + 1*HO) * 42 / 3 - WTI.
    # RBOB/HO quote in $/gallon, 42 gallons per barrel.
    if {"rbob_close", "heatoil_close", "wti_close"} <= set(panel.columns):
        panel["crack321"] = (
            (2 * panel["rbob_close"] + panel["heatoil_close"]) * 42.0 / 3.0
            - panel["wti_close"]
        )
        # gasoline-only crack, as a robustness alternative
        panel["crack_gas"] = panel["rbob_close"] * 42.0 - panel["wti_close"]
        print(f"crack321 built: mean {panel['crack321'].mean():.2f} $/bbl, "
              f"range {panel['crack321'].min():.1f}..{panel['crack321'].max():.1f}")

    # --- returns ---
    px = {c[:-6]: c for c in panel.columns if c.endswith("_close")}
    for name, col in px.items():
        panel[f"{name}_ret"] = np.log(panel[col]).diff()

    # Brent-WTI spread (level and change) -- a refining/transport stress proxy
    if {"brent_close", "wti_close"} <= set(panel.columns):
        panel["bw_spread"] = panel["brent_close"] - panel["wti_close"]
        panel["bw_spread_chg"] = panel["bw_spread"].diff()

    # crack-spread changes: the margin signal. Level matters too (a $30 crack is
    # a good margin environment regardless of yesterday's move), so both the
    # 1d change and a slow z-score of the level are carried forward.
    if "crack321" in panel.columns:
        panel["crack321_chg"] = panel["crack321"].diff()
        panel["crack321_chg5"] = panel["crack321"].diff(5)
        panel["crack321_chg21"] = panel["crack321"].diff(21)
        # level z-score against a 1-year trailing window: strictly backward
        roll = panel["crack321"].rolling(252, min_periods=120)
        panel["crack321_z"] = (panel["crack321"] - roll.mean()) / roll.std()

    # crude in INR terms: what an Indian refiner actually pays
    if {"brent_close", "USDINR_close"} <= set(panel.columns):
        panel["brent_inr_close"] = panel["brent_close"] * panel["USDINR_close"]
        panel["brent_inr_ret"] = np.log(panel["brent_inr_close"]).diff()

    # --- OMC equal-weight basket (the 3 names are ~0.8 correlated: trade the basket) ---
    omc_rets = [f"{n}_ret" for n in OMC if f"{n}_ret" in panel.columns]
    panel["OMC_ret"] = panel[omc_rets].mean(axis=1)

    # --- forward targets: tradable from the NSE close of day t ---
    for name in list(OMC) + ["OMC"] + list(UPSTREAM):
        col = f"{name}_ret"
        if col in panel.columns:
            panel[f"{name}_fwd1"] = panel[col].shift(-1)
            panel[f"{name}_fwd5"] = panel[col].rolling(5).sum().shift(-5)

    out = PROC / f"panel_{source}.csv"
    panel.to_csv(out, index=False)
    print(f"\npanel: {panel.shape[0]} rows x {panel.shape[1]} cols -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
