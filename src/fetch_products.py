"""Phase 1c: refined-product futures, for the refining-margin (crack) signal.

Why
---
Phase 2 killed the crude-PRICE signal: large gross edge, equal cost bill, and
all of the positive contribution confined to 2022-2026. Phase 2's section 7
named the redirection -- model the MECHANISM, not the price. The economic chain
is:

    crude price -> refining margin -> OMC earnings -> OMC share price

Crude price is only the first link, and it enters OMC margins with the wrong
sign AND with policy noise on top. The refining margin itself is the variable
that actually drives OMC profitability, and unlike Singapore GRM or Brent-Dubai
(both paywalled) the US 3-2-1 crack spread is free and daily:

    crack_321 = (2*RBOB + 1*HeatingOil) * 42 / 3  -  WTI      [$/bbl]

RBOB and heating oil trade in $/gallon; 42 gallons to a barrel. The 3-2-1 ratio
approximates a typical refinery yield (2 parts gasoline, 1 part distillate per
3 parts crude).

Caveat recorded up front: this is a US Gulf Coast margin proxy, not an Indian
one. Indian refiners run a different crude slate and product mix, and since 2022
a Russian-discount advantage the US crack does not see. Global product cracks are
nonetheless highly correlated, so this is a usable proxy -- but the gap is a real
limitation, not a formality, and it caps how much confidence any result deserves.
"""
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import START, END  # noqa: E402

RAW = ROOT / "data" / "raw"

PRODUCTS = {
    "rbob": "RB=F",   # $/gallon
    "heatoil": "HO=F",  # $/gallon
    "natgas": "NG=F",   # $/mmBtu -- refinery energy input, control variable
}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    rc = 0
    for name, ticker in PRODUCTS.items():
        df = yf.download(ticker, start=START, end=END,
                         auto_adjust=False, progress=False)
        if df is None or df.empty:
            print(f"FAIL {name} ({ticker})", file=sys.stderr)
            rc = 1
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        out = pd.DataFrame({
            "server_time": pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize(),
            "open": df["Open"], "high": df["High"],
            "low": df["Low"], "close": df["Close"],
        }).dropna(subset=["close"]).sort_values("server_time")
        path = RAW / f"product_{name}_D1.csv"
        out.to_csv(path, index=False)
        print(f"{name:8s} {ticker:6s} {len(out):5d} rows  "
              f"{out.server_time.min().date()} -> {out.server_time.max().date()}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
