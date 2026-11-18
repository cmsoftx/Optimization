"""Integration tests on the real pipeline outputs (skipped until `python main.py all` has run)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import get_path, load_config
from src.preprocessing import to_snake

OUT = get_path("outputs_dir", create=False)
NEEDED = ["selected_allocation.csv", "selected_warehouses.csv", "optimized_delivery_routes.csv",
          "vehicle_assignments.csv", "warehouse_optimization_results.csv"]
pytestmark = pytest.mark.skipif(not all((OUT / f).exists() for f in NEEDED), reason="run the pipeline first")


def test_consistency_checks_all_pass():
    from src.evaluation import consistency_checks
    c = consistency_checks()
    assert c["passed"].all(), c[~c["passed"]]


def test_no_mainland_island_routes():
    st = pd.read_csv(OUT / "optimized_delivery_routes.csv")
    wh = pd.read_csv(OUT / "selected_warehouses.csv").set_index("warehouse_id")["network"]
    assert (st["network"].values == wh.reindex(st["warehouse_id"]).values).all()
    pr = st[st["network"] == "Puerto Rico"]
    assert pr["lat"].between(17.8, 18.6).all() and pr["lon"].between(-67.3, -65.2).all()
    us = st[st["network"] == "CONUS"]
    assert us["lon"].lt(-66.9).all() and us["lat"].gt(24).all()


def test_cflp_is_reproducible():
    from src.warehouse_cflp import build_problem, solve_cflp
    res = pd.read_csv(OUT / "warehouse_optimization_results.csv").set_index("network")
    for net in ["CONUS", "Puerto Rico"]:
        sol = solve_cflp(build_problem(net))
        assert sol.objective == pytest.approx(res.loc[net, "opening_cost"] + res.loc[net, "transport_cost"], rel=1e-6)


def test_solver_report_is_honest():
    r = pd.read_csv(OUT / "cflp_solver_report.csv")
    assert (r["proven_optimal"] == (r["termination"] == "optimal")).all()


def test_warehouse_comparison_consistent():
    c = pd.read_csv(OUT / "warehouse_algorithm_comparison.csv")
    for net, g in c.groupby("network"):
        cflp = g[g["method"].str.startswith("CFLP")]["total_cost"].iat[0]
        # no heuristic or baseline may beat a proven-optimal CFLP solution
        assert (g["total_cost"] >= cflp - 1e-6).all()


def test_outputs_have_no_personal_data():
    pii = set(load_config()["dataset"]["pii_columns"]) | {to_snake(c) for c in load_config()["dataset"]["pii_columns"]}
    pii |= {"customer_zipcode", "customer_id"}
    for f in OUT.glob("*.csv"):
        cols = set(pd.read_csv(f, nrows=0).columns)
        if f.name in {"phase1_column_profile.csv", "phase2_column_mapping.csv", "phase1_data_dictionary.csv"}:
            continue  # metadata about column names, not data
        assert not (cols & pii), f"{f.name} exposes {cols & pii}"


def test_experiment_outputs_exist_and_are_finite():
    for f in ["experiment_warehouse_comparison.csv", "experiment_routing_comparison.csv", "forecast_impact_comparison.csv",
              "sensitivity_analysis.csv", "robustness_analysis.csv", "final_performance_summary.csv"]:
        d = pd.read_csv(OUT / f)
        assert len(d) > 0, f
    s = pd.read_csv(OUT / "final_performance_summary.csv")
    assert set(s["source"]) <= {"actual", "forecast", "simulated"}
