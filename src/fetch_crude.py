"""Phase 0: export daily crude OHLCV from MetaTrader 5 to data/raw/.

Writes one CSV per symbol with the broker-server timestamp preserved verbatim.
Raw files are immutable -- never edit them, re-run to refresh.
"""
import datetime as dt
import sys
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.instruments import CRUDE, START, END  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def fetch(symbol: str, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"cannot select {symbol}: {mt5.last_error()}")
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1, start, end)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"no rates for {symbol}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    # server time (EET/EEST). Kept as-is; alignment happens in build_panel.py
    df["server_time"] = pd.to_datetime(df["time"], unit="s")
    df = df[["server_time", "open", "high", "low", "close", "tick_volume", "real_volume", "spread"]]
    return df.sort_values("server_time").reset_index(drop=True)


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}", file=sys.stderr)
        return 1
    try:
        ti = mt5.terminal_info()
        print(f"terminal: {ti.company} connected={ti.connected}")
        start = dt.datetime.fromisoformat(START) - dt.timedelta(days=10)
        end = dt.datetime.fromisoformat(END) + dt.timedelta(days=1)
        for name, symbol in CRUDE.items():
            df = fetch(symbol, start, end)
            out = RAW / f"crude_{name}_{symbol}_D1.csv"
            df.to_csv(out, index=False)
            print(f"{name:6s} {symbol:6s} {len(df):5d} rows  "
                  f"{df.server_time.min().date()} -> {df.server_time.max().date()}  -> {out.name}")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
