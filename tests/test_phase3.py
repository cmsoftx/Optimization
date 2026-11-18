"""Phase 3 tests: leakage-free features, chronology, recursion consistency, metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import forecasting as fc
from src.config import get_path, load_config

PROC = get_path("processed_dir", create=False)
OUT = get_path("outputs_dir", create=False)


def _toy_panel(Z: int = 6, T: int = 60, gran: str = "W", seed: int = 0) -> fc.Panel:
    rng = np.random.default_rng(seed)
    freq = load_config()["forecasting"]["granularity"][gran]["period_freq"]
    periods = pd.period_range("2015-01-04", periods=T, freq=freq)
    zones = pd.DataFrame({"zone_id": [f"Z{i}" for i in range(Z)],
                          "network": ["CONUS"] * (Z - 2) + ["Puerto Rico"] * 2,
                          "centroid_lat": rng.uniform(20, 45, Z), "centroid_lon": rng.uniform(-120, -66, Z),
                          "dominant_city": "x", "dominant_state": "y"})
    zones["is_pr"] = (zones["network"] == "Puerto Rico").astype(int)
    O = rng.poisson(rng.uniform(0.3, 5, (Z, 1)), (Z, T)).astype(float)
    U = O * rng.integers(1, 4, (Z, T))
    return fc.Panel(gran, periods, zones, {"orders": O, "units": U})


@pytest.mark.parametrize("gran", ["W", "M"])
def test_features_do_not_use_current_or_future_values(gran):
    """Changing y at period t (and later) must not change any feature at periods <= t."""
    p = _toy_panel(gran=gran)
    F0 = fc.feature_matrices(p.Y, p.zones, p.periods, gran)
    for t in [5, 20, 40]:
        Y1 = {k: v.copy() for k, v in p.Y.items()}
        Y1["orders"][:, t:] += 100.0
        Y1["units"][:, t:] *= 7.0
        F1 = fc.feature_matrices(Y1, p.zones, p.periods, gran)
        for name in F0:
            a, b = F0[name][:, : t + 1], F1[name][:, : t + 1]
            assert np.allclose(a, b, equal_nan=True), f"{name} leaks future information at t={t}"


def test_lag_and_rolling_values_are_correct():
    p = _toy_panel()
    F = fc.feature_matrices(p.Y, p.zones, p.periods, "W")
    O = p.Y["orders"]
    t = 30
    assert np.allclose(F["orders_lag1"][:, t], O[:, t - 1])
    assert np.allclose(F["orders_lag4"][:, t], O[:, t - 4])
    assert np.allclose(F["orders_rmean4"][:, t], O[:, t - 4:t].mean(axis=1))
    assert np.allclose(F["orders_rmean13"][:, t], O[:, t - 13:t].mean(axis=1))
    assert np.allclose(F["orders_expmean"][:, t], O[:, :t].mean(axis=1))
    conus = p.zones["network"].eq("CONUS").to_numpy()
    assert np.allclose(F["net_orders_lag1"][conus, t], O[conus, t - 1].sum())
    s13 = O[:, t - 13:t].sum(axis=1)
    assert np.allclose(F["zone_share13"][conus, t], s13[conus] / s13[conus].sum())


def test_recursive_features_match_batch_features_when_predictions_equal_actuals():
    """horizon() rebuilds features from history + predictions. If the 'predictions'
    were the actuals, the features must equal the batch features."""
    p = _toy_panel()
    F = fc.feature_matrices(p.Y, p.zones, p.periods, "W")
    origin = 40
    Yx = {k: v[:, : origin + 2] for k, v in p.Y.items()}
    Fr = fc.feature_matrices(Yx, p.zones, p.periods[: origin + 2], "W")
    for name in F:
        assert np.allclose(F[name][:, origin + 1], Fr[name][:, -1], equal_nan=True), name


def test_split_chronology_real_config():
    """Train < validation < test for both splits, and the post-break test starts at the break."""
    p = _toy_panel(T=165)
    for split in ["pre_break", "post_break"]:
        warm, tr, va, te = fc._split_indices(p, split)
        assert tr.max() < va.min() and va.max() < te.min()
        assert tr.min() >= warm
    _, _, _, te = fc._split_indices(p, "post_break")
    brk = pd.Timestamp(load_config()["preprocessing"]["regime_break_date"])
    assert p.periods[te[0]].start_time == brk
    assert p.periods[te[0] - 1].end_time < brk


def test_metrics_and_mape_guard():
    m = fc.metrics([1, 2, 3], [1, 2, 6])
    assert m["MAE"] == pytest.approx(1.0)
    assert m["RMSE"] == pytest.approx(np.sqrt(3))
    assert m["WAPE"] == pytest.approx(3 / 6)
    assert m["MAPE"] == pytest.approx(1 / 3)
    assert np.isnan(fc.metrics([0, 2], [1, 2])["MAPE"])  # undefined with zero actuals


def test_baseline_predictions_definition():
    p = _toy_panel()
    frame = fc.long_frame(p)
    fm = fc.FittedModels("W", ma_window={"orders": 4, "units": 8})
    row = frame[frame["t"] == 30]
    O = p.Y["orders"]
    assert np.allclose(fm.predict("historical_average", "orders", row), O[:, :30].mean(axis=1))
    assert np.allclose(fm.predict("moving_average", "orders", row), O[:, 26:30].mean(axis=1))


def test_horizon_baselines_are_flat_and_never_see_test_actuals():
    p = _toy_panel()
    fm = fc.FittedModels("W", ma_window={"orders": 4, "units": 4})
    h = fc.horizon(fm, p, origin=39, H=5, models=("moving_average",))
    Y2 = {k: v.copy() for k, v in p.Y.items()}
    Y2["orders"][:, 40:] = 999
    p2 = fc.Panel(p.gran, p.periods, p.zones, Y2)
    h2 = fc.horizon(fm, p2, origin=39, H=5, models=("moving_average",))
    assert np.allclose(h["predicted"], h2["predicted"])  # test actuals do not affect forecasts
    for _, g in h[h["target"] == "orders"].groupby("zone_id"):
        assert g["predicted"].nunique() == 1


def test_ml_pipeline_end_to_end_on_toy_panel():
    """Fit RF/XGB on a toy panel and check that the recursive horizon ignores test actuals."""
    p = _toy_panel(T=50)
    frame = fc.long_frame(p)
    tr, va = frame[frame["t"].between(13, 34)], frame[frame["t"].between(35, 41)]
    fm = fc.tune_and_fit(tr, va, "W", seed=1)
    assert set(fm.rf) == set(fm.xgb) == {"orders", "units"}
    h1 = fc.horizon(fm, p, origin=41, H=4, models=("xgboost", "random_forest"))
    Y2 = {k: v.copy() for k, v in p.Y.items()}
    Y2["orders"][:, 42:] = 1e3
    h2 = fc.horizon(fm, fc.Panel(p.gran, p.periods, p.zones, Y2), origin=41, H=4,
                    models=("xgboost", "random_forest"))
    assert np.allclose(h1["predicted"], h2["predicted"])
    assert (h1["predicted"] >= 0).all()


# ----------------------------------------------------------------------------- real outputs
HAVE = (OUT / "forecast_evaluation.csv").exists()
real = pytest.mark.skipif(not HAVE, reason="run `python main.py forecast` first")


@real
def test_real_predictions_nonnegative_and_complete():
    d = pd.read_csv(OUT / "demand_predictions.csv")
    assert (d["predicted"] >= 0).all()
    assert d["zone_id"].notna().all()


@real
def test_real_cflp_input_covers_all_forecast_zones():
    c = pd.read_csv(OUT / "cflp_zone_demand_forecast.csv")
    z = pd.read_csv(OUT / "demand_zones.csv")
    nets = load_config()["forecasting"]["networks"]
    assert set(c["zone_id"]) == set(z[z["network"].isin(nets)]["zone_id"])
    assert (c[["forecast_per_period_orders", "forecast_per_period_units"]] >= 0).all().all()


@real
def test_real_selected_model_is_best_on_selection_set():
    sel = pd.read_csv(OUT / "selected_forecast_model.csv")
    e = pd.read_csv(OUT / "forecast_evaluation.csv")
    e = e[(e["granularity"] == "W") & (e["eval_set"] == "post_break_adapted") & (e["tier"] == "all")
          & (e["level"] == "zone_total") & (e["model"] != fc.ORACLE)]
    for r in sel.itertuples():
        assert np.isclose(e[(e["target"] == r.target) & (e["network"] == r.network)]["WAPE"].min(), r.WAPE)
