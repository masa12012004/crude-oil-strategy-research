"""Phase 5: rebuild the strategy around Phase 4's execution finding, with a
6-level crude regime filter.

Usage:  python src/phase5_rebuild.py [mt5|yf]      (default: yf)

WHAT PHASE 4 CHANGED
--------------------
Phase 4 split each stock's response to crude across the trading day and found
70-104% of it lands in the overnight gap close[t-1] -> open[t]. The crude bar
dated t-1 closes ~03:30 IST on day t: AFTER the NSE close on t-1, BEFORE the
open on t. So the gap spans the information arrival and nobody can trade it --
to be positioned for it you must enter at close[t-1], before the bar exists.

That means Phase 3's structure B, which enters at open[t] on bar t-1 and exits
at open[t+1], earns from two separate things:
  (a) the INTRADAY residual of bar t-1   (small: ONGC +0.055, OIL +0.040)
  (b) a BLIND overnight exposure to bar t, captured via crude momentum
      persistence -- it never sees bar t, it bets bar t looks like bar t-1.

Phase 5 separates them by running the same signal through four execution
variants, so the question "where does this strategy's money actually come
from" gets an answer instead of an assumption.

  o2o   open[t] -> open[t+1]     Phase 3's baseline. (a) + (b).
  o2c   open[t] -> close[t]      Intraday only, flat overnight. (a) alone.
  c2o   close[t] -> open[t+1]    Overnight only. (b) alone.
  c2c   close[t-1] -> close[t]   The naive same-row join. LOOKAHEAD BY
                                 CONSTRUCTION: it enters at close[t-1], hours
                                 before the bar it trades on exists. Included
                                 as a control to price the phantom edge.
                                 (Phase 1 did NOT do this -- it used
                                 c[t] -> c[t+1], entering after the bar closed,
                                 which is clean. Phase 2 used open->close and
                                 Phase 3 open->open. All three were honest.)

THE 6-LEVEL REGIME
------------------
Phase 4 showed direction is regime-dependent: upstream stays positive, refiners
flip sign in 2024. Phase 0's five named regimes are calendar slices chosen with
hindsight and cannot be used in a live rule. This builds a causal substitute:

  vol state   trailing 60d Brent realised vol, bucketed against the EXPANDING
              33rd/67th percentile of its own history to date      -> low/mid/high
  trend state sign of trailing 120d Brent cumulative return        -> down/up

  regime = vol_state * 2 + trend_state                             -> 6 levels

Every input is backward-looking, so the state is known before the open of each
day. The filter then disables the regimes whose TRAIN mean net return is not
positive. Selection happens inside the walk-forward, on training data only.

OVERFITTING NOTE, STATED PLAINLY
--------------------------------
The 2024-2026 holdout was spent in Phase 2 and the regime filter adds six more
on/off switches to a parameter grid that already has 120 combinations. The only
defence is that nothing is ever selected on data the test year can see, and the
filtered result is always printed next to the unfiltered one. If the filter does
not beat the baseline out of sample, it is noise and is reported as noise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.strategy import build_legs, stats, COST_BPS_ONE_WAY  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"

LOOKBACKS = [1, 3, 5, 10, 20, 40]
THRESHOLDS = [0.0, 0.5, 0.75, 1.0, 1.5]
HOLDS = [1, 3, 5, 10]
MIN_TRAIN_YEARS = 5
MIN_ACTIVE = 150
MIN_REGIME_OBS = 60          # a regime needs this many TRAIN days to be judged

VOL_WIN = 60
TREND_WIN = 120
TARGET_VOL = 0.15
MAX_LEVERAGE = 1.0

REGIME_NAMES = {
    0: "low vol / down", 1: "low vol / up",
    2: "mid vol / down", 3: "mid vol / up",
    4: "high vol / down", 5: "high vol / up",
}


# --------------------------------------------------------------------------
# returns per execution variant
# --------------------------------------------------------------------------
def add_variants(p: pd.DataFrame) -> pd.DataFrame:
    """Upstream-basket return under each execution variant.

    All are aligned so that row t is the return earned by a position that was
    DECIDED before the open of day t. build_legs already gives UP_o2c and
    UP_o2o on that convention; c2o and c2c are added here.
    """
    out = p.copy()
    legs = ["ONGC", "OIL"]
    # close[t] -> open[t+1]: entered at the close of the same day the signal
    # was known at the open. Later than the signal, so still legitimate.
    out["UP_c2o"] = pd.concat(
        [np.log(out[f"{n}_open"].shift(-1) / out[f"{n}_close"]) for n in legs],
        axis=1).mean(axis=1)
    # close[t-1] -> close[t]: the naive same-row join. Entering at close[t-1]
    # is IMPOSSIBLE on a signal from the bar that closes 03:30 IST on day t.
    # Kept only as the lookahead control.
    out["UP_c2c"] = pd.concat(
        [np.log(out[f"{n}_close"] / out[f"{n}_close"].shift(1)) for n in legs],
        axis=1).mean(axis=1)
    return out


VARIANTS = {
    "o2o": ("UP_o2o", "diff"),    # hold through, trade only the change
    "o2c": ("UP_o2c", "full"),    # flat every close -> full round trip daily
    "c2o": ("UP_c2o", "full"),    # flat every open  -> full round trip daily
    "c2c": ("UP_c2c", "diff"),
}


# --------------------------------------------------------------------------
# the causal 6-level regime
# --------------------------------------------------------------------------
def regime_state(p: pd.DataFrame) -> pd.Series:
    """0..5, known before the open of each row's day. Strictly backward."""
    b = p["brent_ret"]
    vol = b.rolling(VOL_WIN, min_periods=40).std()
    # expanding percentiles of the vol series itself: no future information,
    # and no fixed threshold smuggled in from looking at the whole sample
    q33 = vol.expanding(min_periods=252).quantile(0.33)
    q67 = vol.expanding(min_periods=252).quantile(0.67)
    vol_state = pd.Series(np.where(vol <= q33, 0, np.where(vol <= q67, 1, 2)),
                          index=p.index, dtype=float)
    vol_state[vol.isna() | q33.isna()] = np.nan
    trend = b.rolling(TREND_WIN, min_periods=80).sum()
    trend_state = (trend > 0).astype(float)
    trend_state[trend.isna()] = np.nan
    return (vol_state * 2 + trend_state).rename("regime")


def make_signal(p: pd.DataFrame, sig_col: str, lookback: int,
                threshold: float, hold: int) -> pd.Series:
    mom = p[sig_col].rolling(lookback).sum()
    z = mom / mom.rolling(VOL_WIN).std()
    raw = np.sign(z).where(z.abs() >= threshold, 0.0).clip(lower=0.0)
    return raw.rolling(hold).mean().fillna(0.0).clip(-1.0, 1.0)


def run(p: pd.DataFrame, variant: str, lookback: int, threshold: float, hold: int,
        allowed: set | None = None, weights: dict | None = None,
        sig_col: str = "brent_ret",
        cost_bps: float = COST_BPS_ONE_WAY) -> pd.DataFrame:
    ret_col, turn_mode = VARIANTS[variant]
    pos = make_signal(p, sig_col, lookback, threshold, hold)
    if allowed is not None:
        # hard filter: the regime is either traded or it is not
        keep = p["regime"].isin(list(allowed)).fillna(False)
        pos = pos.where(keep, 0.0)
    elif weights is not None:
        # soft filter: scale exposure by how well the regime did on train.
        # Unknown / thin regimes get 0.5 rather than 0 or 1.
        pos = pos * p["regime"].map(weights).fillna(0.5)
    ret = p[ret_col]
    turnover = (pos.abs() * 2.0) if turn_mode == "full" else pos.diff().abs().fillna(pos.abs())
    gross = pos * ret
    cost = turnover * cost_bps / 1e4
    return pd.DataFrame({"pos": pos, "ret": ret, "gross": gross,
                         "turnover": turnover, "cost": cost,
                         "net": gross - cost, "regime": p["regime"]},
                        index=p.index).dropna(subset=["ret"])


def select_params(train: pd.DataFrame, variant: str):
    """Grid search on train only, by net Sharpe. Tie-break to larger hold."""
    best, best_key = None, None
    for lb in LOOKBACKS:
        for thr in THRESHOLDS:
            for h in HOLDS:
                bt = run(train, variant, lb, thr, h)
                if int((bt["pos"] != 0).sum()) < MIN_ACTIVE:
                    continue
                s = stats(bt)
                if "sharpe" not in s or not np.isfinite(s["sharpe"]):
                    continue
                key = (s["sharpe"], h, lb)
                if best_key is None or key > best_key:
                    best_key, best = key, (lb, thr, h, s["sharpe"])
    return best


def select_regimes(train: pd.DataFrame, variant: str, lb, thr, h):
    """Keep the regimes whose TRAIN mean net return is positive."""
    bt = run(train, variant, lb, thr, h)
    act = bt[bt["pos"] != 0]
    allowed = set()
    detail = {}
    for r in range(6):
        seg = act[act["regime"] == r]
        if len(seg) < MIN_REGIME_OBS:
            detail[r] = (len(seg), np.nan, False)
            continue
        m = float(seg["net"].mean() * 252 * 100)
        ok = m > 0
        detail[r] = (len(seg), m, ok)
        if ok:
            allowed.add(r)
    return allowed, detail


def select_regime_weights(train: pd.DataFrame, variant: str, lb, thr, h) -> dict:
    """Soft version of select_regimes: exposure 0..1 proportional to train edge.

    The hard filter can switch the whole strategy off for a year at a time,
    because crude regimes persist. Scaling keeps some exposure in every state
    and makes the regime a tilt rather than a switch.
    """
    bt = run(train, variant, lb, thr, h)
    act = bt[bt["pos"] != 0]
    means = {}
    for r in range(6):
        seg = act[act["regime"] == r]
        means[r] = float(seg["net"].mean() * 252 * 100) if len(seg) >= MIN_REGIME_OBS \
            else np.nan
    best = np.nanmax(list(means.values())) if np.isfinite(
        list(means.values())).any() else np.nan
    if not np.isfinite(best) or best <= 0:
        return {r: 0.5 for r in range(6)}
    return {r: (0.5 if not np.isfinite(m) else float(np.clip(m / best, 0.0, 1.0)))
            for r, m in means.items()}


def vol_target_asset(net: pd.Series, asset_ret: pd.Series) -> pd.Series:
    """Scale by the trailing vol of the UNDERLYING, as Phase 3c did."""
    rv = asset_ret.rolling(VOL_WIN, min_periods=40).std().shift(1) * np.sqrt(252)
    lev = (TARGET_VOL / rv).clip(upper=MAX_LEVERAGE)
    return net * lev.reindex(net.index).fillna(0.0)


def vol_target(net: pd.Series) -> pd.Series:
    """De-risk only: scale by target/realised, leverage capped at 1.0.

    Realised vol uses a strictly backward window and is SHIFTED one day, so the
    scale applied on day t cannot see day t's own return.
    """
    rv = net.rolling(VOL_WIN, min_periods=40).std() * np.sqrt(252)
    lev = (TARGET_VOL / rv).clip(upper=MAX_LEVERAGE).shift(1)
    return net * lev.fillna(0.0)


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "yf"
    OUT.mkdir(parents=True, exist_ok=True)
    p = add_variants(build_legs(
        pd.read_csv(PROC / f"panel_{source}.csv", parse_dates=["date"]).set_index("date")))
    p["regime"] = regime_state(p)

    report: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        report.append(s)

    say("=" * 100)
    say("PHASE 5 -- REBUILD ON PHASE 4's EXECUTION FINDING, WITH A 6-LEVEL CRUDE REGIME")
    say(f"source {source}   cost {COST_BPS_ONE_WAY:.0f} bps one-way   "
        f"min train {MIN_TRAIN_YEARS}y")
    say("=" * 100)

    # ---------------- regime description (causal, full sample) --------------
    say("")
    say("THE 6 REGIME LEVELS  (causal: expanding vol percentiles, 120d trend sign)")
    say("-" * 100)
    say(f"   {'regime':<18}{'days':>7}{'% of sample':>13}{'Brent vol%':>12}"
        f"{'upstream o2o %/yr':>20}")
    reg = p.dropna(subset=["regime"])
    bvol = p["brent_ret"].rolling(VOL_WIN, min_periods=40).std() * np.sqrt(252) * 100
    for r in range(6):
        m = reg["regime"] == r
        if not m.any():
            continue
        say(f"   {REGIME_NAMES[r]:<18}{int(m.sum()):>7}{100 * m.mean():>12.1f}%"
            f"{bvol[reg.index][m].mean():>12.1f}"
            f"{reg.loc[m, 'UP_o2o'].mean() * 252 * 100:>20.2f}")
    say("")
    say("   (last column is BUY-AND-HOLD upstream in that regime, not a strategy)")

    # ---------------- walk-forward ------------------------------------------
    years = sorted({d.year for d in p.index})
    CANDIDATES = [
        ("V1", "o2o", None,     "Phase 3 baseline: open->open, no regime filter"),
        ("V2", "o2c", None,     "intraday only, flat overnight"),
        ("V3", "c2o", None,     "overnight only, flat intraday"),
        ("V4", "c2c", None,     "close->close LOOKAHEAD CONTROL (not tradable)"),
        ("V5", "o2o", "filter", "open->open + 6-level regime ON/OFF filter"),
        ("V6", "o2o", "scale",  "open->open + 6-level regime EXPOSURE SCALING"),
    ]

    summary, series = [], {}
    for tag, variant, reg_mode, label in CANDIDATES:
        say("")
        say("-" * 100)
        say(f"[{tag}] {label}")
        say(f"   {'year':>6} {'look':>5} {'thr':>5} {'hold':>5} {'trainSR':>8} "
            f"{'oosNet%':>9} {'oosSR':>7} {'turn':>6} {'act%':>6}  regimes")
        pieces, chosen, reg_hist = [], [], []
        for y in years:
            if y - years[0] < MIN_TRAIN_YEARS:
                continue
            train = p.loc[: f"{y - 1}-12-31"]
            test = p.loc[f"{y}-01-01": f"{y}-12-31"]
            if len(test) < 60:
                continue
            sel = select_params(train, variant)
            if sel is None:
                continue
            lb, thr, h, tr_sr = sel
            allowed, weights = None, None
            rtxt = "all"
            if reg_mode == "filter":
                allowed, _ = select_regimes(train, variant, lb, thr, h)
                if not allowed:
                    allowed = set(range(6))      # never go fully flat on noise
                    rtxt = "all (none +ve)"
                else:
                    rtxt = ",".join(str(x) for x in sorted(allowed))
                reg_hist.append(frozenset(allowed))
            elif reg_mode == "scale":
                weights = select_regime_weights(train, variant, lb, thr, h)
                rtxt = " ".join(f"{weights[r]:.1f}" for r in range(6))
            full = run(p, variant, lb, thr, h, allowed, weights)
            seg = full.loc[f"{y}-01-01": f"{y}-12-31"]
            s = stats(seg)
            pieces.append(seg)
            chosen.append((y, lb, thr, h))
            if "sharpe" in s:
                say(f"   {y:>6} {lb:>5} {thr:>5.2f} {h:>5} {tr_sr:>8.2f} "
                    f"{s['net_ann']:>9.2f} {s['sharpe']:>7.2f} "
                    f"{s['turnover_ann']:>6.1f} {s['days_in_mkt']:>6.1f}  {rtxt}")
            else:
                # a filtered year can be 100% flat -- say so instead of hiding it
                say(f"   {y:>6} {lb:>5} {thr:>5.2f} {h:>5} {tr_sr:>8.2f} "
                    f"{0.0:>9.2f} {'flat':>7} {0.0:>6.1f} {0.0:>6.1f}  {rtxt}")
        if not pieces:
            continue
        wf = pd.concat(pieces)
        s = stats(wf, label)
        yr = wf["net"].groupby(wf.index.year).sum() * 100
        say("")
        say(f"   WALK-FORWARD  net {s['net_ann']:+.2f}%/yr  gross {s['gross_ann']:+.2f}%  "
            f"cost {s['cost_ann']:.2f}%  vol {s['vol_ann']:.2f}%")
        say(f"                 Sharpe {s['sharpe']:+.2f}  maxDD {s['max_dd']:.2f}%  "
            f"t {s['t_stat']:+.2f}  +years {int((yr > 0).sum())}/{len(yr)}")
        if reg_mode == "filter" and reg_hist:
            say(f"                 regime set changed {len(set(reg_hist))} times "
                f"in {len(reg_hist)} years")
        summary.append({"tag": tag, "label": label, "variant": variant,
                        "regime": reg_mode, **s,
                        "pos_years": int((yr > 0).sum()), "n_years": len(yr)})
        series[tag] = wf

    # ---------------- vol-targeted version of the winner --------------------
    say("")
    say("=" * 100)
    say("VOL-TARGETED (15%, de-risk only, leverage capped at 1.0)")
    say("-" * 100)
    say("   Two defensible definitions of 'realised vol', reported together so the")
    say("   headline cannot be chosen after the fact:")
    say("     ASSET    scale by trailing vol of UP_o2o     (what Phase 3c used)")
    say("     STRATEGY scale by trailing vol of net PnL    (targets portfolio vol)")
    say("   Both use a backward window shifted one day, and cap leverage at 1.0.")
    say("")
    say(f"   {'':<4}{'structure':<42}{'--- ASSET ---':>22}{'--- STRATEGY ---':>24}")
    say(f"   {'':<4}{'':<42}{'net%':>8}{'SR':>7}{'maxDD%':>7}"
        f"{'net%':>9}{'SR':>7}{'maxDD%':>8}")
    for tag in series:
        wf = series[tag]
        lab = next(c[3] for c in CANDIDATES if c[0] == tag)
        a = stats(wf.assign(net=vol_target_asset(wf["net"], p["UP_o2o"])))
        b = stats(wf.assign(net=vol_target(wf["net"])))
        if "sharpe" not in a or "sharpe" not in b:
            continue
        say(f"   {tag:<4}{lab:<42}{a['net_ann']:>8.2f}{a['sharpe']:>7.2f}"
            f"{a['max_dd']:>7.1f}{b['net_ann']:>9.2f}{b['sharpe']:>7.2f}"
            f"{b['max_dd']:>8.1f}")
    say("")
    say("   Phase 3c reported +7.44%/yr, Sharpe 0.65 for V1 under ASSET scaling.")
    say("   The STRATEGY column is not an improvement to the edge -- it is a")
    say("   different sizing rule, and it de-risks less because the strategy is")
    say("   flat ~35% of the time, which lowers its measured vol.")

    # ---------------- verdict -----------------------------------------------
    say("")
    say("=" * 100)
    say("VERDICT")
    say("")
    S = pd.DataFrame(summary)
    say(f"   {'':<4}{'structure':<48}{'net%':>8}{'SR':>7}{'maxDD%':>9}{'t':>7}{'+yrs':>7}")
    for _, r in S.iterrows():
        say(f"   {r.tag:<4}{r.label:<48}{r.net_ann:>8.2f}{r.sharpe:>7.2f}"
            f"{r.max_dd:>9.2f}{r.t_stat:>7.2f}  {int(r.pos_years)}/{int(r.n_years)}")
    say("")

    tradable = S[S.variant != "c2c"]
    best = tradable.sort_values("sharpe", ascending=False).iloc[0]
    say(f"   best tradable structure: [{best.tag}] {best.label}")
    say("")

    # --- do the 6 regime levels earn their place? --------------------------
    # All three variants trade the same dates, so this is already like for
    # like. Both regime formulations are compared against the unconditioned
    # baseline; the filter is only worth keeping if one of them wins.
    reg_fair = None
    if {"V1", "V5", "V6"} <= set(series):
        say("   DO THE 6 REGIME LEVELS EARN THEIR PLACE?")
        say(f"     {'':<30}{'net%':>8}{'vol':>7}{'SR':>7}{'maxDD%':>9}{'t':>7}")
        res = {}
        for tag, nm in (("V1", "no regime (baseline)"),
                        ("V5", "6-level on/off filter"),
                        ("V6", "6-level exposure scaling")):
            s_ = stats(series[tag])
            res[tag] = s_
            say(f"     {nm:<30}{s_['net_ann']:>8.2f}{s_['vol_ann']:>7.2f}"
                f"{s_['sharpe']:>7.2f}{s_['max_dd']:>9.2f}{s_['t_stat']:>7.2f}")
        reg_fair = max(res["V5"]["sharpe"], res["V6"]["sharpe"]) > res["V1"]["sharpe"]
        say(f"     -> regime conditioning "
            f"{'IMPROVES' if reg_fair else 'does NOT improve'} the baseline")
        # how many independent decisions did the filter actually make?
        flat_years = sum(1 for yv in series["V5"]["net"].groupby(
            series["V5"].index.year).std() if yv == 0 or not np.isfinite(yv))
        say(f"     the on/off filter sat out {flat_years} entire year(s): crude "
            f"regimes persist, so 6 levels become a few multi-year bets")
        say("")
    checks = {
        "walk-forward net > 0": best.net_ann > 0,
        "walk-forward Sharpe > 0.5": best.sharpe > 0.5,
        "walk-forward t > 2.0": best.t_stat > 2.0,
        "positive in >=60% of years": best.pos_years / best.n_years >= 0.6,
        "6-level regime filter earns its place": bool(reg_fair),
    }
    for k, v in checks.items():
        say(f"   [{'PASS' if v else 'FAIL'}] {k}")
    say("")
    say(f"   {int(sum(checks.values()))}/{len(checks)} checks passed.")
    say("=" * 100)

    (OUT / f"phase5_rebuild_{source}.txt").write_text("\n".join(report), encoding="utf-8")
    for tag, wf in series.items():
        wf["net"].cumsum().to_csv(OUT / f"phase5_wf_{tag}_{source}.csv")
    print(f"\nwrote outputs/phase5_rebuild_{source}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
