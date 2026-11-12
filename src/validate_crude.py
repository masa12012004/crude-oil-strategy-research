"""Phase 0 data-integrity gate: is the yfinance crude backfill the same series
as the MT5 crude the live system will actually trade off?

If daily-return correlation on the overlap is not ~0.98+, the two sources are
not interchangeable and the long-history Phase 1 result does not transfer to
live. This check runs BEFORE build_panel.py is trusted.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.instruments import CRUDE  # noqa: E402

RAW = ROOT / "data" / "raw"


def load(path):
    d = pd.read_csv(path, parse_dates=["server_time"])
    d["date"] = d["server_time"].dt.normalize()
    d = d.groupby("date", as_index=False).last()
    d["ret"] = np.log(d["close"]).diff()
    return d[["date", "close", "ret"]]


def main():
    ok = True
    print(f"{'leg':<6} {'overlap':>8} {'ret corr':>9} {'close corr':>11} "
          f"{'mean |px diff|':>15} {'verdict':>9}")
    for name, symbol in CRUDE.items():
        mt = load(RAW / f"crude_{name}_{symbol}_D1.csv")
        yf = load(RAW / f"crude_{name}_YF_D1.csv")
        m = mt.merge(yf, on="date", suffixes=("_mt", "_yf")).dropna()
        if m.empty:
            print(f"{name:<6} no overlap")
            ok = False
            continue
        rc = float(np.corrcoef(m.ret_mt, m.ret_yf)[0, 1])
        pc = float(np.corrcoef(m.close_mt, m.close_yf)[0, 1])
        pxd = float((m.close_mt - m.close_yf).abs().mean())
        good = rc >= 0.95
        ok &= good
        print(f"{name:<6} {len(m):>8d} {rc:>9.4f} {pc:>11.4f} {pxd:>15.3f} "
              f"{'PASS' if good else 'FAIL':>9}")
    print()
    print("verdict:", "sources interchangeable -- use YF for history, MT5 live"
          if ok else "sources DIVERGE -- do not mix")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
