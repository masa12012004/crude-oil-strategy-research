"""Phase 2: the strategy, as a pure function. No fitting, no IO.

Structure (mandated by research/phase1_findings.md section 6)
------------------------------------------------------------
Dollar-neutral relative value:
    long  upstream basket (ONGC, OIL)      weight +0.5
    short OMC basket (IOC, HINDPETRO, BPCL) weight -0.5
Gross exposure 1.0, net 0.0.

Signal: z = brent_ret / rolling_sd(brent_ret), where brent_ret at row t is the
return of the crude bar that closed 03:30 IST on day t -- i.e. strictly before
the 09:15 NSE open we trade at. Crude up => upstream outperforms OMCs => long
the spread.

Threshold + multi-day hold are required, not optional: Phase 1 measured ~18-21
bps of edge per trade against ~15-25 bps of round-trip cost, so a daily-
rebalanced version cannot clear costs by construction.

Two execution variants, both honest:
  intraday : enter at open_t, exit at close_t. Flat overnight. This is the
             variant Phase 1 actually measured (IC was computed on open->close).
  overnight: enter at open_t, hold to open_t+1. Carries gap risk that Phase 1
             never measured. Reported for comparison, not as the headline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

UPSTREAM_LEGS = ["ONGC", "OIL"]
OMC_LEGS = ["IOC", "HINDPETRO", "BPCL"]

# One-way transaction cost per unit of notional traded, in basis points.
# NSE all-in for these names: brokerage + STT + exchange txn + stamp + GST +
# impact. ~10 bps one-way => ~20 bps to enter and exit a unit of gross. The
# short leg must be done in stock futures (no overnight cash shorts in India);
# IOC/BPCL/HINDPETRO are all F&O-eligible. Futures are cheaper on STT but add
# roll and basis cost, so 10 bps one-way is a reasonable blended figure.
COST_BPS_ONE_WAY = 10.0


def build_legs(p: pd.DataFrame) -> pd.DataFrame:
    """Add equal-weight basket open/close and the per-variant spread returns."""
    out = p.copy()
    for tag, legs in (("UP", UPSTREAM_LEGS), ("OMC", OMC_LEGS)):
        # equal-weight the legs in RETURN space, not price space
        o2c = pd.concat(
            [np.log(out[f"{n}_close"] / out[f"{n}_open"]) for n in legs], axis=1
        ).mean(axis=1)
        o2o = pd.concat(
            [np.log(out[f"{n}_open"].shift(-1) / out[f"{n}_open"]) for n in legs],
            axis=1,
        ).mean(axis=1)
        out[f"{tag}_o2c"] = o2c
        out[f"{tag}_o2o"] = o2o
    # spread return per unit of LONG-SPREAD exposure, at weights +0.5 / -0.5
    out["spread_o2c"] = 0.5 * (out["UP_o2c"] - out["OMC_o2c"])
    out["spread_o2o"] = 0.5 * (out["UP_o2o"] - out["OMC_o2o"])
    return out


def signal(p: pd.DataFrame, threshold: float, hold: int, vol_window: int = 60,
           lookback: int = 1) -> pd.Series:
    """Target spread exposure in [-1, 1], known before the open of each row's day.

    Every input is lagged or same-row-but-pre-open:
      brent_ret at row t  -> crude bar closed 03:30 IST on day t
      rolling sd          -> uses rows <= t, all equally pre-open

    `lookback` is the crude momentum horizon in days. lookback=1 is the raw
    daily return Phase 1 measured. Larger lookbacks are motivated by the TRAIN
    grid's cost diagnosis, not by the holdout: a 1-day crude return flips sign
    constantly, so sign(z) churns the position ~250x/yr and the ~25% gross edge
    is handed entirely to the broker. A multi-day momentum turns over far less
    for a similar gross signal.
    """
    mom = p["brent_ret"].rolling(lookback).sum()
    z = mom / mom.rolling(vol_window).std()
    raw = np.sign(z).where(z.abs() >= threshold, 0.0)
    # multi-day hold: average the last `hold` triggers. This is the standard
    # way to stretch holding period without introducing an entry/exit state
    # machine, and it decays turnover by ~1/hold.
    pos = raw.rolling(hold).mean()
    return pos.fillna(0.0).clip(-1.0, 1.0)


def backtest(p: pd.DataFrame, threshold: float, hold: int,
             variant: str = "intraday", cost_bps: float = COST_BPS_ONE_WAY,
             vol_window: int = 60, lookback: int = 1) -> pd.DataFrame:
    """Return a per-day frame with gross, cost and net spread PnL."""
    if variant not in ("intraday", "overnight"):
        raise ValueError(variant)
    pos = signal(p, threshold, hold, vol_window, lookback)
    ret = p["spread_o2c"] if variant == "intraday" else p["spread_o2o"]

    if variant == "intraday":
        # flat at every close -> the whole position is traded in and out daily
        turnover = pos.abs() * 2.0
    else:
        # only the change in position is traded
        turnover = pos.diff().abs().fillna(pos.abs())

    gross = pos * ret
    cost = turnover * cost_bps / 1e4
    out = pd.DataFrame({
        "pos": pos, "ret": ret, "gross": gross,
        "turnover": turnover, "cost": cost, "net": gross - cost,
    }, index=p.index)
    return out.dropna(subset=["ret"])


def stats(bt: pd.DataFrame, label: str = "") -> dict:
    """Annualised performance on the NET series. 252 NSE trading days."""
    n = bt["net"]
    if len(n) < 30 or n.std() == 0:
        return {"label": label, "n": len(n)}
    ann = 252
    eq = n.cumsum()
    dd = (eq - eq.cummax()).min()
    active = bt["pos"] != 0
    return {
        "label": label,
        "n": int(len(n)),
        "days_in_mkt": float(100 * active.mean()),
        "gross_ann": float(bt["gross"].mean() * ann * 100),
        "cost_ann": float(bt["cost"].mean() * ann * 100),
        "net_ann": float(n.mean() * ann * 100),
        "vol_ann": float(n.std() * np.sqrt(ann) * 100),
        "sharpe": float(n.mean() / n.std() * np.sqrt(ann)),
        "max_dd": float(dd * 100),
        "hit": float(100 * (n[active] > 0).mean()) if active.any() else np.nan,
        "turnover_ann": float(bt["turnover"].mean() * ann),
        "t_stat": float(n.mean() / (n.std() / np.sqrt(len(n)))),
    }
