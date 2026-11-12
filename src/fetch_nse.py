"""Phase 0: download split/bonus-adjusted NSE daily OHLCV + macro to data/raw/."""
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.instruments import OMC, UPSTREAM, MACRO, START, END  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def fetch(ticker: str) -> pd.DataFrame:
    # auto_adjust=True -> OHLC adjusted for splits AND dividends.
    # These are high-dividend PSUs; for a price-signal study adjusted series is
    # the right choice (total-return consistent), and we note it in research/.
    df = yf.download(ticker, start=START, end=END, auto_adjust=True,
                     progress=False, actions=True)
    if df is None or df.empty:
        raise RuntimeError(f"no data for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "date"
    return df.reset_index()


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    groups = {"omc": OMC, "upstream": UPSTREAM, "macro": MACRO}
    rc = 0
    for group, mapping in groups.items():
        for name, ticker in mapping.items():
            try:
                df = fetch(ticker)
            except Exception as e:
                print(f"FAIL {group}/{name} ({ticker}): {e}", file=sys.stderr)
                rc = 1
                continue
            out = RAW / f"{group}_{name}_D1.csv"
            df.to_csv(out, index=False)
            print(f"{group:8s} {name:10s} {len(df):5d} rows  "
                  f"{df.date.min().date()} -> {df.date.max().date()}  -> {out.name}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
