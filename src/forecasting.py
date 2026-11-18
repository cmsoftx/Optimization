"""Phase 3: zone-level demand forecasting (orders and units).

Design
------
* **Panel.** One series per demand zone (CONUS + Puerto Rico), aggregated
  from the zero-filled zone x day table into complete weeks (Sun-Sat, primary)
  or calendar months (alternative). The week of 2017-10-01 starts exactly at
  the distribution break.
* **Leakage-free features.** ``feature_matrices`` builds every feature for
  period *t* from columns ``< t`` only, using prefix sums. The same function
  serves training, one-step evaluation and recursive multi-step forecasting,
  so all three see identical feature definitions.
  ``tests/test_phase3.py`` perturbs future values and checks that past
  features do not change.
* **Approaches.** Historical average (expanding mean), moving average (window
  chosen on validation), Random Forest and XGBoost. The two ML models are
  global (pooled over zones and both networks) with a ``is_pr`` flag; one
  model per target.
* **Evaluation.** Two modes:
    - ``one_step``: forecast period *t* from actuals up to *t-1* (walk-forward).
    - ``horizon``: from a fixed origin, forecast the whole test window
      recursively, without seeing any test actuals. This is how CFLP inputs
      are produced.
  Three evaluation sets: pre-break test, post-break test (models never see
  post-break data) and a post-break *adapted* test (the first
  ``adapt_periods`` post-break periods are observed and used to recalibrate
  the level before forecasting the rest).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from itertools import product

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from xgboost import XGBRegressor

from .config import get_path, load_config

log = logging.getLogger(__name__)
TARGETS = ("orders", "units")
ML_MODELS = ("random_forest", "xgboost")
BASELINES = ("historical_average", "moving_average")
ALL_MODELS = BASELINES + ML_MODELS


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
@dataclass
class Panel:
    gran: str
    periods: pd.PeriodIndex
    zones: pd.DataFrame          # zone_id, network, centroid_lat, centroid_lon, is_pr (row order = matrix rows)
    Y: dict                      # target -> (Z, T) float array

    @property
    def T(self) -> int:
        return len(self.periods)

    def period_index(self, start: str | pd.Timestamp, end: str | pd.Timestamp | None = None) -> np.ndarray:
        """Indices of periods fully inside [start, end] (period start >= start, period end <= end)."""
        s = self.periods.start_time >= pd.Timestamp(start)
        if end is not None:
            s &= self.periods.end_time.normalize() <= pd.Timestamp(end)
        return np.flatnonzero(s)

    def first_index_from(self, date) -> int:
        return int(np.flatnonzero(self.periods.start_time >= pd.Timestamp(date))[0])


def build_panel(zone_daily: pd.DataFrame, zones: pd.DataFrame, gran: str = "W") -> Panel:
    """Aggregate zone x day demand to complete periods for the forecasting networks."""
    cfg = load_config()["forecasting"]
    freq = cfg["granularity"][gran]["period_freq"]
    zd = zone_daily[zone_daily["network"].isin(cfg["networks"])].copy()
    zd["period"] = zd["date"].dt.to_period(freq)
    days = zd.groupby("period")["date"].nunique()
    expected = pd.Series({p: (p.end_time.normalize() - p.start_time).days + 1 for p in days.index})
    complete = days.index[days.values == expected.reindex(days.index).values]
    zd = zd[zd["period"].isin(complete)]
    agg = zd.groupby(["zone_id", "period"])[["orders", "units"]].sum()
    zmeta = (zones[zones["network"].isin(cfg["networks"])]
             [["zone_id", "network", "centroid_lat", "centroid_lon", "dominant_city", "dominant_state"]]
             .sort_values(["network", "zone_id"]).reset_index(drop=True))
    zmeta["is_pr"] = (zmeta["network"] == "Puerto Rico").astype(int)
    periods = pd.PeriodIndex(sorted(complete), freq=freq)
    idx = pd.MultiIndex.from_product([zmeta["zone_id"], periods], names=["zone_id", "period"])
    agg = agg.reindex(idx, fill_value=0)
    Y = {t: agg[t].to_numpy(dtype=float).reshape(len(zmeta), len(periods)) for t in TARGETS}
    return Panel(gran, periods, zmeta, Y)


# --------------------------------------------------------------------------- #
# Features (strictly past-only)
# --------------------------------------------------------------------------- #
def _prefix(X: np.ndarray) -> np.ndarray:
    """S[:, t] = sum of columns < t  (shape Z x (T+1))."""
    return np.concatenate([np.zeros((X.shape[0], 1)), np.cumsum(X, axis=1)], axis=1)


def _roll_sum(S: np.ndarray, T: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Sum and count of the last w columns before each t (t = 0..T-1)."""
    t = np.arange(T)
    lo = np.maximum(t - w, 0)
    return S[:, t] - S[:, lo], (t - lo).astype(float)


def _lag(X: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(X, np.nan)
    if k < X.shape[1]:
        out[:, k:] = X[:, :-k]
    return out


def feature_matrices(Y: dict, zones: pd.DataFrame, periods: pd.PeriodIndex, gran: str) -> dict[str, np.ndarray]:
    """Return {feature_name: (Z, T) array}. Feature at column t uses only columns < t."""
    g = load_config()["forecasting"]["granularity"][gran]
    O, U = Y["orders"], Y["units"]
    Z, T = O.shape
    F: dict[str, np.ndarray] = {}
    net_codes = zones["network"].to_numpy()
    for name, X in (("orders", O), ("units", U)):
        S = _prefix(X)
        for k in g["lags"]:
            F[f"{name}_lag{k}"] = _lag(X, k)
        for w in g["windows"]:
            s, c = _roll_sum(S, T, w)
            with np.errstate(invalid="ignore", divide="ignore"):
                F[f"{name}_rmean{w}"] = np.where(c > 0, s / c, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            F[f"{name}_expmean"] = np.where(np.arange(T) > 0, S[:, :T] / np.arange(T), np.nan)
        # network totals (same value for all zones of a network)
        NX = np.zeros_like(X)
        for net in np.unique(net_codes):
            m = net_codes == net
            NX[m] = X[m].sum(axis=0, keepdims=True)
        NS = _prefix(NX)
        F[f"net_{name}_lag1"] = _lag(NX, 1)
        wl = g["windows"][0]
        s, c = _roll_sum(NS, T, wl)
        with np.errstate(invalid="ignore", divide="ignore"):
            F[f"net_{name}_rmean{wl}"] = np.where(c > 0, s / c, np.nan)
        if name == "orders":
            NO_S = NS
    w_long = g["windows"][-1]
    So, Su = _prefix(O), _prefix(U)
    so, c = _roll_sum(So, T, w_long)
    su, _ = _roll_sum(Su, T, w_long)
    sq, _ = _roll_sum(_prefix(O ** 2), T, w_long)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(c > 0, so / c, np.nan)
        F[f"orders_rstd{w_long}"] = np.sqrt(np.maximum(np.where(c > 0, sq / c, np.nan) - mean ** 2, 0))
        zero_s, _ = _roll_sum(_prefix((O == 0).astype(float)), T, w_long)
        F[f"orders_zero_frac{w_long}"] = np.where(c > 0, zero_s / c, np.nan)
        # units per order: zone level over long window, network level over short window
        nso, _ = _roll_sum(NO_S, T, w_long)
        F[f"zone_share{w_long}"] = np.where(nso > 0, so / nso, np.nan)
        F[f"units_per_order{w_long}"] = np.where(so > 0, su / so, np.nan)
        NU = np.zeros_like(U); NO = np.zeros_like(O)
        for net in np.unique(net_codes):
            m = net_codes == net
            NU[m] = U[m].sum(axis=0, keepdims=True); NO[m] = O[m].sum(axis=0, keepdims=True)
        nu1, _ = _roll_sum(_prefix(NU), T, g["windows"][0])
        no1, _ = _roll_sum(_prefix(NO), T, g["windows"][0])
        F["net_units_per_order"] = np.where(no1 > 0, nu1 / no1, np.nan)
    # fall back to the network ratio when a zone had no orders in the window
    F[f"units_per_order{w_long}"] = np.where(np.isnan(F[f"units_per_order{w_long}"]),
                                             F["net_units_per_order"], F[f"units_per_order{w_long}"])
    # static + calendar (known in advance, no leakage)
    F["centroid_lat"] = np.repeat(zones["centroid_lat"].to_numpy()[:, None], T, axis=1)
    F["centroid_lon"] = np.repeat(zones["centroid_lon"].to_numpy()[:, None], T, axis=1)
    F["is_pr"] = np.repeat(zones["is_pr"].to_numpy()[:, None], T, axis=1).astype(float)
    start = periods.start_time
    cal = start.isocalendar().week.to_numpy().astype(float) if gran == "W" else start.month.to_numpy().astype(float)
    F["period_of_year"] = np.repeat(cal[None, :], Z, axis=0)
    return F


FEATURE_ORDER_CACHE: dict[str, list[str]] = {}


def feature_names(gran: str) -> list[str]:
    if gran not in FEATURE_ORDER_CACHE:
        z = pd.DataFrame({"network": ["CONUS"], "centroid_lat": [0.0], "centroid_lon": [0.0], "is_pr": [0]})
        per = pd.period_range("2015-01-04", periods=3, freq=load_config()["forecasting"]["granularity"][gran]["period_freq"])
        FEATURE_ORDER_CACHE[gran] = list(feature_matrices({"orders": np.zeros((1, 3)), "units": np.zeros((1, 3))},
                                                          z, per, gran))
    return FEATURE_ORDER_CACHE[gran]


def long_frame(panel: Panel, Y: dict | None = None) -> pd.DataFrame:
    """Rows = (zone, period) with targets and features."""
    Y = Y or panel.Y
    F = feature_matrices(Y, panel.zones, panel.periods, panel.gran)
    Z, T = Y["orders"].shape
    df = pd.DataFrame({"zone_idx": np.repeat(np.arange(Z), T), "t": np.tile(np.arange(T), Z)})
    df["zone_id"] = panel.zones["zone_id"].to_numpy()[df["zone_idx"]]
    df["network"] = panel.zones["network"].to_numpy()[df["zone_idx"]]
    df["period_start"] = panel.periods.start_time[df["t"]]
    for tgt in TARGETS:
        df[f"y_{tgt}"] = Y[tgt].reshape(-1)
    for k, v in F.items():
        df[k] = v.reshape(-1)
    return df


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def _X(df: pd.DataFrame, gran: str) -> np.ndarray:
    return df[feature_names(gran)].to_numpy(dtype=float)


def _X_rf(df: pd.DataFrame, gran: str) -> np.ndarray:
    return np.nan_to_num(_X(df, gran), nan=0.0)  # RF cannot take NaN; NaN only in rare early cells


@dataclass
class FittedModels:
    gran: str
    ma_window: dict = field(default_factory=dict)          # target -> k
    rf: dict = field(default_factory=dict)                 # target -> estimator
    xgb: dict = field(default_factory=dict)
    rf_params: dict = field(default_factory=dict)
    xgb_params: dict = field(default_factory=dict)
    tuning: list = field(default_factory=list)

    def predict(self, model: str, target: str, df: pd.DataFrame) -> np.ndarray:
        if model == "historical_average":
            p = df[f"{target}_expmean"].to_numpy()
        elif model == "moving_average":
            p = df[f"{target}_rmean{self.ma_window[target]}"].to_numpy()
        elif model == "random_forest":
            p = self.rf[target].predict(_X_rf(df, self.gran))
        elif model == "xgboost":
            p = self.xgb[target].predict(_X(df, self.gran))
        else:
            raise ValueError(model)
        return np.clip(np.nan_to_num(p, nan=0.0), 0, None)


def wape(y, p) -> float:
    y, p = np.asarray(y, float), np.asarray(p, float)
    d = np.abs(y).sum()
    return float(np.abs(y - p).sum() / d) if d > 0 else float("nan")


def tune_and_fit(train: pd.DataFrame, valid: pd.DataFrame, gran: str, seed: int) -> FittedModels:
    """Choose hyper-parameters on the validation window (one-step WAPE).

    The returned models are fitted on TRAIN only. Use :func:`refit` to retrain
    on train+validation with the chosen settings.
    """
    cfg = load_config()["forecasting"]
    fm = FittedModels(gran)
    Xtr, Xva = _X(train, gran), _X(valid, gran)
    for tgt in TARGETS:
        ytr, yva = train[f"y_{tgt}"].to_numpy(), valid[f"y_{tgt}"].to_numpy()
        # moving-average window
        best = min(cfg["granularity"][gran]["ma_candidates"],
                   key=lambda k: wape(yva, np.nan_to_num(valid[f"{tgt}_rmean{k}"])))
        fm.ma_window[tgt] = best
        for k in cfg["granularity"][gran]["ma_candidates"]:
            fm.tuning.append({"target": tgt, "model": "moving_average", "params": f"window={k}",
                              "valid_wape": wape(yva, np.nan_to_num(valid[f"{tgt}_rmean{k}"])),
                              "selected": k == best})
        # random forest
        best_rf, best_w = None, np.inf
        for params in cfg["random_forest_grid"]:
            rf = RandomForestRegressor(n_estimators=cfg["random_forest_trees"], random_state=seed, n_jobs=-1, **params)
            rf.fit(np.nan_to_num(Xtr), ytr)
            w = wape(yva, np.clip(rf.predict(np.nan_to_num(Xva)), 0, None))
            fm.tuning.append({"target": tgt, "model": "random_forest", "params": str(params), "valid_wape": w,
                              "selected": False})
            if w < best_w:
                best_rf, best_w, fm.rf_params[tgt] = rf, w, params
        fm.rf[tgt] = best_rf
        _mark_selected(fm.tuning, tgt, "random_forest", str(fm.rf_params[tgt]))
        # xgboost
        grid = cfg["xgboost_grid"]
        fixed = dict(cfg["xgboost_fixed"])
        es = fixed.pop("early_stopping_rounds")
        best_x, best_w = None, np.inf
        for obj, depth, mcw in product(grid["objective"], grid["max_depth"], grid["min_child_weight"]):
            params = dict(objective=obj, max_depth=depth, min_child_weight=mcw)
            xgb = XGBRegressor(**fixed, **params, random_state=seed, n_jobs=4, tree_method="hist",
                               early_stopping_rounds=es, eval_metric="mae")
            xgb.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
            w = wape(yva, np.clip(xgb.predict(Xva), 0, None))
            params["n_estimators"] = int(xgb.best_iteration) + 1
            fm.tuning.append({"target": tgt, "model": "xgboost", "params": str(params), "valid_wape": w,
                              "selected": False})
            if w < best_w:
                best_x, best_w, fm.xgb_params[tgt] = xgb, w, params
        fm.xgb[tgt] = best_x
        _mark_selected(fm.tuning, tgt, "xgboost", str(fm.xgb_params[tgt]))
    return fm


def _mark_selected(rows: list, tgt: str, model: str, params: str) -> None:
    for r in rows:
        if r["target"] == tgt and r["model"] == model and r["params"] == params:
            r["selected"] = True


def refit(fm: FittedModels, data: pd.DataFrame, seed: int) -> FittedModels:
    """Refit RF/XGB with the chosen hyper-parameters on ``data`` (train + validation)."""
    cfg = load_config()["forecasting"]
    fixed = {k: v for k, v in cfg["xgboost_fixed"].items() if k not in ("early_stopping_rounds", "n_estimators")}
    out = FittedModels(fm.gran, dict(fm.ma_window), {}, {}, dict(fm.rf_params), dict(fm.xgb_params), list(fm.tuning))
    X = _X(data, fm.gran)
    for tgt in TARGETS:
        y = data[f"y_{tgt}"].to_numpy()
        rf = RandomForestRegressor(n_estimators=cfg["random_forest_trees"], random_state=seed, n_jobs=-1,
                                   **fm.rf_params[tgt])
        out.rf[tgt] = rf.fit(np.nan_to_num(X), y)
        xgb = XGBRegressor(**fixed, **fm.xgb_params[tgt], random_state=seed, n_jobs=4, tree_method="hist")
        out.xgb[tgt] = xgb.fit(X, y)
    return out


# --------------------------------------------------------------------------- #
# Forecasting modes
# --------------------------------------------------------------------------- #
def one_step(fm: FittedModels, frame: pd.DataFrame, t_idx: np.ndarray, models=ALL_MODELS) -> pd.DataFrame:
    """Walk-forward forecasts for periods ``t_idx`` using actual history up to t-1."""
    rows = frame[frame["t"].isin(t_idx)]
    out = []
    for tgt in TARGETS:
        for m in models:
            out.append(pd.DataFrame({"zone_id": rows["zone_id"].values, "network": rows["network"].values,
                                     "t": rows["t"].values, "period_start": rows["period_start"].values,
                                     "target": tgt, "model": m, "actual": rows[f"y_{tgt}"].values,
                                     "predicted": fm.predict(m, tgt, rows)}))
    return pd.concat(out, ignore_index=True)


def horizon(fm: FittedModels, panel: Panel, origin: int, H: int, models=ALL_MODELS,
            actual: bool = True) -> pd.DataFrame:
    """Forecast periods origin+1 .. origin+H from information up to ``origin`` only.

    Baselines are flat (their value at origin+1). ML models are recursive: each
    predicted period is appended to the history, and features for the next
    period are rebuilt with the same leakage-free function. Both targets are
    predicted jointly at each step because features use both series.
    """
    Z = len(panel.zones)
    hist = {t: panel.Y[t][:, : origin + 1].copy() for t in TARGETS}
    ext_periods = pd.period_range(panel.periods[0], periods=origin + 1 + H, freq=panel.periods.freq)
    out = []
    for m in models:
        Yh = {t: hist[t].copy() for t in TARGETS}
        preds = {t: np.zeros((Z, H)) for t in TARGETS}
        for h in range(H):
            # append a placeholder column, compute features for it (uses columns < it only)
            Yx = {t: np.concatenate([Yh[t], np.zeros((Z, 1))], axis=1) for t in TARGETS}
            F = feature_matrices(Yx, panel.zones, ext_periods[: Yx["orders"].shape[1]], panel.gran)
            row = pd.DataFrame({k: v[:, -1] for k, v in F.items()})
            for t in TARGETS:
                if m in BASELINES and h > 0:
                    preds[t][:, h] = preds[t][:, 0]  # flat
                else:
                    preds[t][:, h] = fm.predict(m, t, row)
            for t in TARGETS:
                Yh[t] = np.concatenate([Yh[t], preds[t][:, h:h + 1]], axis=1)
        for t in TARGETS:
            for h in range(H):
                tt = origin + 1 + h
                act = panel.Y[t][:, tt] if (actual and tt < panel.T) else np.full(Z, np.nan)
                out.append(pd.DataFrame({"zone_id": panel.zones["zone_id"].values,
                                         "network": panel.zones["network"].values, "t": tt,
                                         "period_start": ext_periods[tt].start_time, "target": t, "model": m,
                                         "actual": act, "predicted": preds[t][:, h]}))
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def metrics(y, p) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    e = p - y
    out = {"n": len(y), "actual_total": y.sum(), "predicted_total": p.sum(),
           "MAE": np.abs(e).mean(), "RMSE": np.sqrt((e ** 2).mean()), "WAPE": wape(y, p),
           "bias_pct": e.sum() / y.sum() if y.sum() > 0 else np.nan}
    # MAPE is defined only when every actual is strictly positive
    out["MAPE"] = float(np.mean(np.abs(e) / y)) if (y > 0).all() else np.nan
    return out


def zone_tiers(panel: Panel, train_end_t: int) -> pd.Series:
    """high / medium / low tier per zone by mean training orders, within each network."""
    tc = load_config()["forecasting"]["zone_tiers"]
    vol = pd.Series(panel.Y["orders"][:, :train_end_t].mean(axis=1), index=panel.zones["zone_id"])
    tiers = pd.Series("low", index=vol.index)
    for net, zids in panel.zones.groupby("network")["zone_id"]:
        r = vol[zids].rank(ascending=False, method="first") / len(zids)
        tiers[r[r <= tc["high"]].index] = "high"
        tiers[r[(r > tc["high"]) & (r <= tc["high"] + tc["medium"])].index] = "medium"
    return tiers


def evaluate(pred: pd.DataFrame, tiers: pd.Series, keys: dict) -> pd.DataFrame:
    """Metrics at zone-period, network-period and zone-total levels, by network and tier."""
    rows = []
    p = pred.assign(tier=pred["zone_id"].map(tiers))
    group_cols = ["target", "model"] + (["handling"] if "handling" in p else [])
    for gkey, g in p.groupby(group_cols):
        base = dict(keys, **dict(zip(group_cols, gkey if isinstance(gkey, tuple) else (gkey,))))
        for net in ["CONUS", "Puerto Rico", "ALL"]:
            gn = g if net == "ALL" else g[g["network"] == net]
            if gn.empty:
                continue
            for tier in ["all", "high", "medium", "low"]:
                gt = gn if tier == "all" else gn[gn["tier"] == tier]
                if gt.empty:
                    continue
                m = metrics(gt["actual"], gt["predicted"]); m["MAPE"] = np.nan  # zone-period: zeros present
                rows.append(dict(base, network=net, tier=tier, level="zone_period", **m))
                zt = gt.groupby("zone_id")[["actual", "predicted"]].sum()
                m = metrics(zt["actual"], zt["predicted"]); m["MAPE"] = np.nan
                rows.append(dict(base, network=net, tier=tier, level="zone_total", **m))
            if net != "ALL":
                npd = gn.groupby("t")[["actual", "predicted"]].sum()
                rows.append(dict(base, network=net, tier="all", level="network_period",
                                 **metrics(npd["actual"], npd["predicted"])))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Post-break adaptation
# --------------------------------------------------------------------------- #
def recalibration_factors(onestep_adapt: pd.DataFrame) -> pd.DataFrame:
    """Network-level level-correction factor = actual / predicted over the adaptation window."""
    s = onestep_adapt.groupby(["network", "target", "model"])[["actual", "predicted"]].sum()
    s["factor"] = s["actual"] / s["predicted"].replace(0, np.nan)
    return s.reset_index()


def share_x_level(panel: Panel, origin: int, adapt: int, H: int) -> pd.DataFrame:
    """Structured diagnostic: zone share (full history to origin) x network level (last ``adapt`` periods)."""
    out = []
    for t in TARGETS:
        Y = panel.Y[t][:, : origin + 1]
        for net, idx in panel.zones.groupby("network").groups.items():
            idx = np.asarray(list(idx))
            share = Y[idx].sum(axis=1) / Y[idx].sum()
            level = Y[idx][:, -adapt:].sum(axis=0).mean()
            for h in range(H):
                tt = origin + 1 + h
                out.append(pd.DataFrame({"zone_id": panel.zones["zone_id"].values[idx], "network": net, "t": tt,
                                         "period_start": panel.periods[tt].start_time, "target": t,
                                         "model": "share_x_recent_level", "actual": panel.Y[t][idx, tt],
                                         "predicted": share * level}))
    return pd.concat(out, ignore_index=True)


def post_break_average(panel: Panel, origin: int, adapt: int, H: int) -> pd.DataFrame:
    """Regime-reset baseline: each zone's mean over the ``adapt`` observed post-break periods only.
    It discards all pre-break history, so it can follow a *spatial* relocation of demand
    (e.g. Puerto Rico), which a network-level recalibration cannot."""
    out = []
    for t in TARGETS:
        lvl = panel.Y[t][:, origin + 1 - adapt: origin + 1].mean(axis=1)
        for h in range(H):
            tt = origin + 1 + h
            act = panel.Y[t][:, tt] if tt < panel.T else np.full(len(lvl), np.nan)
            out.append(pd.DataFrame({"zone_id": panel.zones["zone_id"].values, "network": panel.zones["network"].values,
                                     "t": tt, "period_start": panel.periods[tt].start_time, "target": t,
                                     "model": "post_break_average", "actual": act, "predicted": lvl}))
    return pd.concat(out, ignore_index=True)


ORACLE = "oracle_window_mean"


def oracle_reference(pred: pd.DataFrame) -> pd.DataFrame:
    """NOT A FORECAST. Each zone's actual mean over the evaluation window, used as a constant
    prediction. This is the best any constant-rate forecast could do, so its error shows
    the irreducible noise floor of zone-period demand (mostly Poisson-like count noise)."""
    one = pred[pred["model"] == pred["model"].iat[0]].copy()
    if "handling" in one:
        one = one[one["handling"] == one["handling"].iat[0]]
    one["predicted"] = one.groupby(["target", "zone_id"])["actual"].transform("mean")
    one["model"] = ORACLE
    one["handling"] = "reference"
    return one


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
@dataclass
class ForecastRun:
    gran: str
    panel: Panel
    predictions: pd.DataFrame
    evaluation: pd.DataFrame
    tuning: pd.DataFrame
    models: dict                 # split -> FittedModels (refitted)
    factors: pd.DataFrame
    importance: pd.DataFrame
    timings: dict


def _split_indices(panel: Panel, split: str) -> tuple[int, np.ndarray, np.ndarray, np.ndarray]:
    cfg = load_config()["forecasting"]
    s = cfg["splits"][split]
    warm = cfg["granularity"][panel.gran]["warmup"]
    val_start = panel.first_index_from(s["validation_start"])
    test_idx = panel.period_index(s["test_start"], s["test_end"])
    train_idx = np.arange(warm, val_start)
    val_idx = np.arange(val_start, test_idx[0])
    return warm, train_idx, val_idx, test_idx


def run_forecasting(zone_daily: pd.DataFrame, zones: pd.DataFrame, gran: str = "W") -> ForecastRun:
    cfg = load_config()
    seed = cfg["project"]["random_seed"]
    fc = cfg["forecasting"]
    panel = build_panel(zone_daily, zones, gran)
    frame = long_frame(panel)
    preds, evals, tunings, models, factors, timings = [], [], [], {}, [], {}

    # tiers fixed from the pre-break training window, so every evaluation uses the same zone groups
    _, tr0, _, _ = _split_indices(panel, "pre_break")
    tiers = zone_tiers(panel, tr0[-1] + 1)

    for split in ["pre_break", "post_break"]:
        warm, tr, va, te = _split_indices(panel, split)
        train, valid = frame[frame["t"].isin(tr)], frame[frame["t"].isin(va)]
        t0 = time.perf_counter()
        fm = tune_and_fit(train, valid, gran, seed)
        tune_s = time.perf_counter() - t0
        tunings.append(pd.DataFrame(fm.tuning).assign(split=split, granularity=gran))
        # validation predictions (models fitted on train only)
        vpred = one_step(fm, frame, va).assign(eval_set=f"{split}_validation", mode="one_step", handling="none")
        t0 = time.perf_counter()
        fm = refit(fm, frame[frame["t"].isin(np.r_[tr, va])], seed)
        timings[split] = {"tune_s": tune_s, "refit_s": time.perf_counter() - t0}
        models[split] = fm
        os_ = one_step(fm, frame, te).assign(eval_set=f"{split}_test", mode="one_step", handling="none")
        hz = horizon(fm, panel, te[0] - 1, len(te)).assign(eval_set=f"{split}_test", mode="horizon", handling="none")
        orc = oracle_reference(os_.assign(handling="none")).assign(eval_set=f"{split}_test", mode="reference")
        preds += [vpred, os_, hz, orc]
        for p in (vpred, os_, hz):
            evals.append(evaluate(p.drop(columns="handling"), tiers,
                                  {"granularity": gran, "eval_set": p["eval_set"].iat[0], "mode": p["mode"].iat[0],
                                   "handling": "none"}))
        evals.append(evaluate(orc, tiers, {"granularity": gran, "eval_set": f"{split}_test", "mode": "reference"}))

    # ---- post-break adaptation: observe the first `adapt` periods, then forecast the rest
    fm = models["post_break"]
    _, _, _, te = _split_indices(panel, "post_break")
    adapt = fc["granularity"][gran]["adapt_periods"]
    a_idx, rest = te[:adapt], te[adapt:]
    os_adapt = one_step(fm, frame, a_idx)
    fac = recalibration_factors(os_adapt)
    factors.append(fac.assign(granularity=gran))
    hz = horizon(fm, panel, rest[0] - 1, len(rest))
    raw = hz.assign(handling="none")
    rec = hz.merge(fac[["network", "target", "model", "factor"]], on=["network", "target", "model"], how="left")
    rec["predicted"] = rec["predicted"] * rec["factor"].fillna(1.0)
    rec = rec.drop(columns="factor").assign(handling="recalibrated")
    sxl = share_x_level(panel, rest[0] - 1, adapt, len(rest)).assign(handling="regime_reset")
    pba = post_break_average(panel, rest[0] - 1, adapt, len(rest)).assign(handling="regime_reset")
    ad = pd.concat([raw, rec, sxl, pba], ignore_index=True).assign(eval_set="post_break_adapted", mode="horizon")
    orc = oracle_reference(raw).assign(eval_set="post_break_adapted", mode="reference")
    preds += [ad, orc]
    evals.append(evaluate(ad, tiers, {"granularity": gran, "eval_set": "post_break_adapted", "mode": "horizon"}))
    evals.append(evaluate(orc, tiers, {"granularity": gran, "eval_set": "post_break_adapted", "mode": "reference"}))

    predictions = pd.concat(preds, ignore_index=True)
    predictions["granularity"] = gran
    predictions["tier"] = predictions["zone_id"].map(tiers)
    imp = feature_importance(models["pre_break"], frame, _split_indices(panel, "pre_break")[3], seed)
    return ForecastRun(gran, panel, predictions, pd.concat(evals, ignore_index=True),
                       pd.concat(tunings, ignore_index=True), models, pd.concat(factors), imp, timings)


def feature_importance(fm: FittedModels, frame: pd.DataFrame, test_idx: np.ndarray, seed: int) -> pd.DataFrame:
    """XGBoost gain / weight / cover, RF impurity importance, and permutation importance
    (increase in test MAE when a feature is shuffled) for both ML models."""
    rows = []
    names = feature_names(fm.gran)
    test = frame[frame["t"].isin(test_idx)]
    for tgt in TARGETS:
        booster = fm.xgb[tgt].get_booster()
        for kind in ("gain", "weight", "cover"):
            sc = booster.get_score(importance_type=kind)
            tot = sum(sc.values()) or 1.0
            for i, n in enumerate(names):
                v = sc.get(f"f{i}", sc.get(n, 0.0))
                rows.append({"granularity": fm.gran, "target": tgt, "model": "xgboost", "importance_type": kind,
                             "feature": n, "importance": v / tot})
        for i, n in enumerate(names):
            rows.append({"granularity": fm.gran, "target": tgt, "model": "random_forest",
                         "importance_type": "impurity", "feature": n,
                         "importance": fm.rf[tgt].feature_importances_[i]})
        y = test[f"y_{tgt}"].to_numpy()
        for model, est, X in (("xgboost", fm.xgb[tgt], _X(test, fm.gran)),
                              ("random_forest", fm.rf[tgt], _X_rf(test, fm.gran))):
            pi = permutation_importance(est, X, y, scoring="neg_mean_absolute_error", n_repeats=5,
                                        random_state=seed, n_jobs=1)
            for i, n in enumerate(names):
                rows.append({"granularity": fm.gran, "target": tgt, "model": model,
                             "importance_type": "permutation_mae_increase", "feature": n,
                             "importance": pi.importances_mean[i], "importance_std": pi.importances_std[i]})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Model selection and CFLP hand-off
# --------------------------------------------------------------------------- #
def model_comparison(evaluation: pd.DataFrame) -> pd.DataFrame:
    """Compact comparison: zone-level WAPE/MAE/RMSE per (granularity, eval set, mode, handling, target,
    network, model), plus each model's rank within its group."""
    e = evaluation[(evaluation["tier"] == "all") & (evaluation["network"] != "ALL")
                   & evaluation["level"].isin(["zone_period", "zone_total"])]
    piv = e.pivot_table(index=["granularity", "eval_set", "mode", "handling", "target", "network", "model"],
                        columns="level", values=["WAPE", "MAE", "RMSE", "bias_pct"]).reset_index()
    piv.columns = ["_".join([c for c in col if c]) for col in piv.columns]
    grp = ["granularity", "eval_set", "mode", "handling", "target", "network"]
    piv["rank_zone_period_wape"] = piv.groupby(grp)["WAPE_zone_period"].rank(method="min")
    return piv.sort_values(grp + ["WAPE_zone_period"]).reset_index(drop=True)


SELECTION_LEVEL = "zone_total"


def select_for_cflp(evaluation: pd.DataFrame, gran: str = "W", level: str = SELECTION_LEVEL) -> pd.DataFrame:
    """Pick, per (target, network), the (model, handling) with the lowest WAPE of **zone totals over
    the post-break adapted test window** (13 weeks). That is the quantity the CFLP consumes, in the
    regime it must plan for. The CFLP is solved separately per network.

    Why not zone-week WAPE? MAE/WAPE on individual zone-weeks is minimised by the conditional
    *median*. For sparse counts (most zone-weeks are 0 or 1) the median is near 0, so that
    criterion rewards systematic under-forecasting. The CFLP needs unbiased *rates*.
    The rule uses TEST results, as the project brief requires. The oracle reference is excluded.
    Near-ties (within 0.01 WAPE) are reported in the Phase 3 report."""
    e = evaluation[(evaluation["granularity"] == gran) & (evaluation["eval_set"] == "post_break_adapted")
                   & (evaluation["tier"] == "all") & (evaluation["level"] == level)
                   & evaluation["network"].isin(load_config()["forecasting"]["networks"])
                   & (evaluation["model"] != ORACLE)]
    best = e.loc[e.groupby(["target", "network"])["WAPE"].idxmin(),
                 ["target", "network", "model", "handling", "WAPE", "MAE", "RMSE", "bias_pct"]]
    return best.assign(selection_level=level).reset_index(drop=True)


def cflp_forecast(run: ForecastRun, selection: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, FittedModels, pd.DataFrame]:
    """Final forward forecast for the CFLP.

    1. Refit every model on ALL complete periods (through the last full period).
    2. If the selected handling is 'recalibrated', estimate the network factor from
       one-step predictions over the last ``adapt_periods`` periods (all post-break).
    3. Forecast ``cflp_horizon_periods`` ahead recursively and summarise per zone.
    The historical-average forecast is exported alongside it for Experiment C.
    """
    cfg = load_config()["forecasting"]
    panel = run.panel
    frame = long_frame(panel)
    warm = cfg["granularity"][panel.gran]["warmup"]
    fm = refit(run.models["post_break"], frame[frame["t"] >= warm], seed)
    H, adapt = cfg["cflp_horizon_periods"], cfg["granularity"][panel.gran]["adapt_periods"]
    origin = panel.T - 1
    hz = horizon(fm, panel, origin, H, actual=False)
    fac = recalibration_factors(one_step(fm, frame, np.arange(panel.T - adapt, panel.T)))
    hz = hz.merge(fac[["network", "target", "model", "factor"]], on=["network", "target", "model"], how="left")
    ext = _extend_panel_nan(panel, H)
    regime = pd.concat([share_x_level(ext, origin, adapt, H), post_break_average(ext, origin, adapt, H)])
    brk = panel.first_index_from(load_config()["preprocessing"]["regime_break_date"])
    rows, paths = [], []
    for tgt in TARGETS:
        hist_all = pd.Series(panel.Y[tgt].mean(axis=1), index=panel.zones["zone_id"])
        hist_post = pd.Series(panel.Y[tgt][:, brk:].mean(axis=1), index=panel.zones["zone_id"])
        for net in selection["network"].unique():
            sel = selection[(selection["target"] == tgt) & (selection["network"] == net)].iloc[0]
            if sel["model"] in ("share_x_recent_level", "post_break_average"):
                p = regime[(regime["target"] == tgt) & (regime["model"] == sel["model"]) & (regime["network"] == net)]
            else:
                p = hz[(hz["target"] == tgt) & (hz["model"] == sel["model"]) & (hz["network"] == net)].copy()
                if sel["handling"] == "recalibrated":
                    p["predicted"] = p["predicted"] * p["factor"].fillna(1.0)
            paths.append(p[["zone_id", "network", "t", "period_start", "target", "predicted"]]
                         .assign(model=sel["model"], handling=sel["handling"]))
            s = p.groupby("zone_id")["predicted"].agg(["mean", "sum"])
            rows.append(pd.DataFrame({
                "zone_id": s.index, "target": tgt, "model": f"{sel['model']} ({sel['handling']})",
                "forecast_per_period": s["mean"].values, "forecast_horizon_total": s["sum"].values,
                "historical_avg_per_period_all": hist_all.reindex(s.index).values,
                "historical_avg_per_period_post_break": hist_post.reindex(s.index).values}))
    long = pd.concat(rows)
    wide = long.pivot(index="zone_id", columns="target",
                      values=["forecast_per_period", "forecast_horizon_total", "model",
                              "historical_avg_per_period_all", "historical_avg_per_period_post_break"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    meta = panel.zones.set_index("zone_id")
    out = meta[["network", "dominant_city", "dominant_state", "centroid_lat", "centroid_lon"]].join(wide).reset_index()
    for c in [c for c in out.columns if c.startswith(("forecast_", "historical_"))]:
        out[c] = out[c].astype(float)
    # Coherence: each order contains >= 1 unit, so a zone's unit forecast cannot be below its order
    # forecast. The two targets can come from different selected models, so enforce it explicitly.
    out["units_coherence_adjustment"] = np.maximum(out["forecast_per_period_orders"] - out["forecast_per_period_units"], 0)
    out["forecast_per_period_units"] += out["units_coherence_adjustment"]
    out["forecast_horizon_total_units"] += out["units_coherence_adjustment"] * H
    out["horizon_periods"] = H
    out["granularity"] = panel.gran
    out["forecast_start"] = (panel.periods[-1] + 1).start_time.date()
    out["forecast_end"] = (panel.periods[-1] + H).end_time.date()
    path = pd.concat(paths, ignore_index=True).assign(eval_set="cflp_forward", mode="horizon", actual=np.nan,
                                                      granularity=panel.gran)
    return out, fm, path


def _extend_panel_nan(panel: Panel, H: int) -> Panel:
    per = pd.period_range(panel.periods[0], periods=panel.T + H, freq=panel.periods.freq)
    Y = {t: np.concatenate([panel.Y[t], np.full((len(panel.zones), H), np.nan)], axis=1) for t in TARGETS}
    return Panel(panel.gran, per, panel.zones, Y)


def save_models(run: ForecastRun, final_fm: FittedModels, selection: pd.DataFrame) -> None:
    d = get_path("models_dir")
    for split, fm in run.models.items():
        joblib.dump(fm, d / f"forecast_models_{run.gran}_{split}.pkl", compress=3)
    joblib.dump({"selection": selection, "models": final_fm, "granularity": run.gran,
                 "feature_names": feature_names(run.gran),
                 "note": "Final models refitted on all complete periods. Use src.forecasting.horizon() to forecast."},
                d / "demand_forecasting_model.pkl", compress=3)


# --------------------------------------------------------------------------- #
# Phase 3 entry point
# --------------------------------------------------------------------------- #
@dataclass
class Phase3Result:
    runs: dict
    evaluation: pd.DataFrame
    comparison: pd.DataFrame
    importance: pd.DataFrame
    selection: pd.DataFrame
    cflp: pd.DataFrame
    predictions_selected: pd.DataFrame
    tuning: pd.DataFrame
    factors: pd.DataFrame


def run_phase3(zone_daily: pd.DataFrame, zones: pd.DataFrame, write: bool = True) -> Phase3Result:
    cfg = load_config()
    seed = cfg["project"]["random_seed"]
    runs = {}
    for gran in ["W", "M"]:
        t0 = time.perf_counter()
        runs[gran] = run_forecasting(zone_daily, zones, gran)
        log.info("granularity %s done in %.1fs", gran, time.perf_counter() - t0)
    evaluation = pd.concat([r.evaluation for r in runs.values()], ignore_index=True)
    comparison = model_comparison(evaluation)
    importance = pd.concat([r.importance for r in runs.values()], ignore_index=True)
    tuning = pd.concat([r.tuning for r in runs.values()], ignore_index=True)
    factors = pd.concat([r.factors for r in runs.values()], ignore_index=True)
    selection = select_for_cflp(evaluation, cfg["forecasting"]["primary_granularity"])
    prim = runs[cfg["forecasting"]["primary_granularity"]]
    cflp, final_fm, fwd = cflp_forecast(prim, selection, seed)

    # actual vs predicted of the selected (model, handling) per target/network, plus the forward path
    pw = prim.predictions
    keep = pw.merge(selection[["target", "network", "model"]], on=["target", "network", "model"])
    keep = keep[(keep["handling"] == "none") | keep.set_index(["target", "network", "model", "handling"]).index.isin(
        selection.set_index(["target", "network", "model", "handling"]).index)]
    sel_pred = pd.concat([keep, fwd], ignore_index=True)
    if write:
        _write_phase3(runs, evaluation, comparison, importance, selection, cflp, sel_pred, tuning, factors, final_fm)
    return Phase3Result(runs, evaluation, comparison, importance, selection, cflp, sel_pred, tuning, factors)


def _write_phase3(runs, evaluation, comparison, importance, selection, cflp, sel_pred, tuning, factors, final_fm):
    out = get_path("outputs_dir")
    cols = ["granularity", "eval_set", "mode", "handling", "model", "target", "network", "tier", "zone_id",
            "period_start", "actual", "predicted"]
    allp = pd.concat([r.predictions for r in runs.values()], ignore_index=True)
    allp["handling"] = allp["handling"].fillna("none")
    allp = allp[allp["eval_set"] != "pre_break_validation"]  # validation kept in evaluation only
    for tgt in TARGETS:
        fname = {"orders": "order_demand_predictions.csv", "units": "unit_demand_predictions.csv"}[tgt]
        allp[allp["target"] == tgt][cols].round({"predicted": 4}).to_csv(out / fname, index=False)
    sel_pred.assign(tier=sel_pred["zone_id"].map(dict(zip(allp["zone_id"], allp["tier"]))))[cols].round(
        {"predicted": 4}).to_csv(out / "demand_predictions.csv", index=False)
    evaluation.to_csv(out / "forecast_evaluation.csv", index=False)
    comparison.to_csv(out / "model_comparison.csv", index=False)
    importance.to_csv(out / "feature_importance.csv", index=False)
    selection.to_csv(out / "selected_forecast_model.csv", index=False)
    cflp.to_csv(out / "cflp_zone_demand_forecast.csv", index=False)
    tuning.to_csv(out / "forecast_hyperparameter_tuning.csv", index=False)
    factors.to_csv(out / "forecast_recalibration_factors.csv", index=False)
    pd.DataFrame([dict(granularity=g, split=k, **v) for g, r in runs.items() for k, v in r.timings.items()]).to_csv(
        out / "forecast_runtimes.csv", index=False)
    save_models(runs["W"], final_fm, selection)
    joblib.dump(runs["M"].models, get_path("models_dir") / "forecast_models_M_all_splits.pkl", compress=3)
