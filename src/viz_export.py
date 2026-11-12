"""Export rolling volatility / correlation / beta series for the 3D visualisation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

WIN = 60          # trading days for rolling stats
ANN = np.sqrt(252)

ASSETS = [
    ("brent", "Brent", "crude"),
    ("wti", "WTI", "crude"),
    ("IOC", "IOC", "omc"),
    ("HINDPETRO", "HPCL", "omc"),
    ("BPCL", "BPCL", "omc"),
    ("ONGC", "ONGC", "upstream"),
    ("OIL", "Oil India", "upstream"),
    ("NIFTY", "Nifty 50", "index"),
]


def main() -> int:
    p = pd.read_csv(PROC / "panel_yf.csv", parse_dates=["date"]).set_index("date")

    vol, corr, beta = {}, {}, {}
    bret = p["brent_ret"]
    bvar = bret.rolling(WIN).var()
    for col, _, _ in ASSETS:
        r = p[f"{col}_ret"]
        vol[col] = r.rolling(WIN).std() * ANN * 100
        corr[col] = r.rolling(WIN).corr(bret)
        beta[col] = r.rolling(WIN).cov(bret) / bvar

    V = pd.DataFrame(vol)
    C = pd.DataFrame(corr)
    B = pd.DataFrame(beta)

    # month-end sampling keeps the surface readable and the payload small
    keep = V.dropna().index
    idx = pd.Series(keep, index=keep).resample("ME").last().dropna()
    dates = pd.DatetimeIndex(idx.values)

    payload = {
        "window": WIN,
        "assets": [{"key": k, "label": l, "group": g} for k, l, g in ASSETS],
        "dates": [d.strftime("%Y-%m") for d in dates],
        "vol": {k: [round(float(x), 2) for x in V.loc[dates, k]] for k, _, _ in ASSETS},
        "corr": {k: [round(float(x), 3) for x in C.loc[dates, k]] for k, _, _ in ASSETS},
        "beta": {k: [round(float(x), 3) for x in B.loc[dates, k]] for k, _, _ in ASSETS},
    }

    # headline figures for the page's annotations, computed not guessed
    summary = {}
    for k, label, _ in ASSETS:
        v = V[k].dropna()
        summary[k] = {
            "label": label,
            "vol_mean": round(float(v.mean()), 1),
            "vol_max": round(float(v.max()), 1),
            "vol_max_date": v.idxmax().strftime("%b %Y"),
            "corr_mean": round(float(C[k].dropna().mean()), 3),
            "corr_pct_neg": round(100 * float((C[k].dropna() < 0).mean()), 1),
            "beta_mean": round(float(B[k].dropna().mean()), 3),
        }
    payload["summary"] = summary

    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "viz_data.json"
    f.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"{len(dates)} months {payload['dates'][0]} .. {payload['dates'][-1]}, "
          f"{len(ASSETS)} assets -> {f} ({f.stat().st_size / 1024:.0f} KB)")
    print()
    print(f"{'asset':<10} {'mean vol%':>10} {'peak vol%':>10} {'peak':>10} "
          f"{'corr brent':>11} {'%neg':>6} {'beta':>7}")
    for k, s in summary.items():
        print(f"{s['label']:<10} {s['vol_mean']:>10.1f} {s['vol_max']:>10.1f} "
              f"{s['vol_max_date']:>10} {s['corr_mean']:>11.3f} "
              f"{s['corr_pct_neg']:>6.1f} {s['beta_mean']:>7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
