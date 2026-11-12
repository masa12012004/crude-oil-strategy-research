"""Phase 0: long-history crude from yfinance, as a backfill for MT5.

Why this exists
---------------
The Exness MT5 demo server only retains ~1,300 daily crude bars (back to
2021-10-27). That is too short for the regime-stability test that Phase 1's gate
depends on (pre-2014 admin pricing, post-dereg, covid, war-discount).

So: ICE Brent (BZ=F) and NYMEX WTI (CL=F) front-month continuous from yfinance
give 2010-> history, and MT5 stays as the live/verification source. The overlap
is correlation-checked in validate_crude.py before either is used.

Timing note: BZ=F / CL=F daily bars are stamped with the US/London trading date
and settle after the 15:30 IST NSE close, exactly like the MT5 bars. The same
avail_date = bar_date + 1 rule applies, so build_panel.py needs no special case.
"""
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import START, END  # noqa: E402

RAW = ROOT / "data" / "raw"

YF_CRUDE = {"brent": "BZ=F", "wti": "CL=F"}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    rc = 0
    for name, ticker in YF_CRUDE.items():
        df = yf.download(ticker, start=START, end=END,
                         auto_adjust=False, progress=False)
        if df is None or df.empty:
            print(f"FAIL {name} ({ticker}): no data", file=sys.stderr)
            rc = 1
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["server_time"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
        out = pd.DataFrame({
            "server_time": df["server_time"],
            "open": df["Open"], "high": df["High"],
            "low": df["Low"], "close": df["Close"],
            "tick_volume": df.get("Volume", 0),
            "real_volume": 0, "spread": 0,
        }).dropna(subset=["close"]).sort_values("server_time")
        path = RAW / f"crude_{name}_YF_D1.csv"
        out.to_csv(path, index=False)
        print(f"{name:6s} {ticker:6s} {len(out):5d} rows  "
              f"{out.server_time.min().date()} -> {out.server_time.max().date()}  -> {path.name}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
