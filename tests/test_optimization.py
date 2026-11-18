"""Phase 4-6 tests on small synthetic instances: CFLP optimality and constraints, GA, routing."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from src.customer_allocation import allocation_table, regret_allocation, warehouse_table
from src.genetic_algorithm import kmeans_baseline, repair, run_ga
from src.vehicle_routing import (DepotInstance, build_depot_instances, largest_remainder, nearest_neighbor,
                                 ortools_solve, route_feasibility)
from src.warehouse_cflp import NetworkProblem, evaluate_configuration, generate_candidates, load_demand, solve_cflp


def toy_problem(capacity=10.0, fixed=50.0, min_p=1, max_p=3, seed=0, n=7) -> NetworkProblem:
    rng = np.random.default_rng(seed)
    zones = pd.DataFrame({"zone_id": [f"Z{i}" for i in range(n)], "network": "CONUS",
                          "centroid_lat": rng.uniform(30, 40, n), "centroid_lon": rng.uniform(-100, -80, n),
                          "dominant_city": "c", "dominant_state": "s",
                          "orders": rng.uniform(1, 5, n).round(2)})
    zones["units"] = zones["orders"] * 1.2
    cand = zones.iloc[:4][["zone_id", "centroid_lat", "centroid_lon", "dominant_city", "dominant_state"]].copy()
    cand.insert(0, "warehouse_id", [f"WH-{k}" for k in range(4)]); cand["source"] = "test"
    from src.distance_calculator import road_distance_matrix
    D = road_distance_matrix(zones["centroid_lat"], zones["centroid_lon"], cand["centroid_lat"], cand["centroid_lon"], 1.2)
    return NetworkProblem("CONUS", zones, cand, D, zones["orders"].to_numpy(), zones["units"].to_numpy(),
                          np.full(4, capacity), np.full(4, fixed), 0.1, 0.5, min_p, max_p)


def brute_force(prob: NetworkProblem) -> float:
    """Exhaustive optimum of the single-sourcing CFLP (tiny instances only)."""
    best = np.inf
    C = prob.C
    for assign in itertools.product(range(prob.n_candidates), repeat=prob.n_zones):
        a = np.array(assign)
        open_mask = np.zeros(prob.n_candidates, bool); open_mask[a] = True
        if not prob.min_warehouses <= open_mask.sum() <= prob.max_warehouses:
            continue
        load = np.bincount(a, weights=prob.units, minlength=prob.n_candidates)
        if (load > prob.capacity + 1e-9).any():
            continue
        best = min(best, prob.fixed_cost[open_mask].sum() + C[np.arange(prob.n_zones), a].sum())
    return best


@pytest.mark.parametrize("capacity,fixed,max_p", [(10.0, 50.0, 3), (8.0, 5.0, 4), (30.0, 200.0, 2)])
def test_cflp_matches_brute_force_optimum(capacity, fixed, max_p):
    prob = toy_problem(capacity, fixed, max_p=max_p)
    sol = solve_cflp(prob)
    assert sol.termination == "optimal"
    assert sol.objective == pytest.approx(brute_force(prob), rel=1e-6)


def test_cflp_constraints_hold():
    prob = toy_problem(capacity=9.0, fixed=20.0)
    sol = solve_cflp(prob)
    ev = evaluate_configuration(prob, sol.open, sol.assign, sol.unserved_fraction)
    assert (sol.assign >= 0).all()                                   # every zone assigned exactly once
    assert sol.open[sol.assign].all()                                # only open warehouses serve
    load = np.bincount(sol.assign, weights=prob.units, minlength=prob.n_candidates)
    assert (load <= prob.capacity + 1e-9).all()                      # capacity
    assert prob.min_warehouses <= sol.n_open <= prob.max_warehouses  # business limit
    assert ev["feasible"] and ev["closed_warehouses_serving"] == 0
    # independent cost recomputation equals solver objective
    assert ev["opening_cost"] + ev["transport_cost"] == pytest.approx(sol.objective, rel=1e-9)


def test_cflp_infeasible_is_reported_not_hidden():
    prob = toy_problem(capacity=2.0, fixed=10.0, max_p=2)  # total units >> 2 warehouses x 2
    with pytest.raises(RuntimeError):
        solve_cflp(prob)
    sol = solve_cflp(prob, allow_unserved=True)
    ev = evaluate_configuration(prob, sol.open, sol.assign, sol.unserved_fraction)
    assert ev["unserved_units"] > 0 and not ev["feasible"]


def test_fixed_open_allocation_subproblem():
    prob = toy_problem(capacity=12.0)
    mask = np.array([True, False, True, False])
    sol = solve_cflp(prob, fixed_open=mask, allow_unserved=True)
    assert (sol.open == mask).all()
    assert set(sol.assign[sol.assign >= 0]) <= {0, 2}


def test_candidates_reproducible_and_real_zones():
    prob = toy_problem(n=7)
    a = generate_candidates(prob.zones, 3, 2, seed=1)
    b = generate_candidates(prob.zones, 3, 2, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert set(a["zone_id"]) <= set(prob.zones["zone_id"])
    assert prob.zones.loc[prob.zones["orders"].idxmax(), "zone_id"] in set(a["zone_id"])


def test_load_demand_validates_columns(tmp_path):
    p = tmp_path / "d.csv"
    pd.DataFrame({"zone_id": ["a"], "network": ["CONUS"]}).to_csv(p, index=False)
    with pytest.raises(KeyError):
        load_demand(p)


def test_regret_allocation_respects_capacity_and_reports_unserved():
    prob = toy_problem(capacity=6.0)
    mask = np.array([True, True, False, False])
    a, _ = regret_allocation(prob, mask)
    load = np.bincount(a[a >= 0], weights=prob.units[a >= 0], minlength=4)
    assert (load <= prob.capacity + 1e-9).all()
    assert set(a[a >= 0]) <= {0, 1}
    if prob.units.sum() > 12:
        assert (a < 0).any()  # cannot fit everything -> unserved, never overloaded


def test_repair_keeps_warehouse_bounds():
    import random
    prob = toy_problem(capacity=100, min_p=2, max_p=3)
    rng = random.Random(0)
    for ind in ([1, 1, 1, 1], [0, 0, 0, 0], [1, 0, 0, 0]):
        assert 2 <= sum(repair(list(ind), prob, rng)) <= 3


def test_ga_finds_optimum_on_toy_and_is_reproducible():
    prob = toy_problem(capacity=10.0, fixed=30.0)
    params = {"population_size": 20, "generations": 30, "patience": 30}
    r1, r2 = run_ga(prob, 7, params), run_ga(prob, 7, params)
    assert (r1.best_open == r2.best_open).all() and r1.best_heuristic_cost == r2.best_heuristic_cost
    exact = solve_cflp(prob, fixed_open=r1.best_open)
    assert exact.objective == pytest.approx(brute_force(prob), rel=1e-6)


def test_kmeans_baseline_opens_k():
    prob = toy_problem(capacity=100)
    sol, _ = kmeans_baseline(prob, 2, 0)
    assert sol.n_open == 2


def test_largest_remainder():
    v = np.array([0.4, 0.4, 1.2, 2.6, 0.0])
    r = largest_remainder(v)
    assert r.sum() == round(v.sum()) and (r >= 0).all() and (np.abs(r - v) < 1).all()


def _instance(packages, cap=5, n_veh=4, max_km=10_000):
    rng = np.random.default_rng(1)
    n = len(packages)
    stops = pd.DataFrame({"stop_id": [f"S{i}" for i in range(n)], "zone_id": [f"Z{i}" for i in range(n)],
                          "lat": 35 + rng.normal(0, 1, n), "lon": -90 + rng.normal(0, 1, n), "packages": packages})
    from src.distance_calculator import road_distance_matrix
    lat, lon = np.r_[35, stops["lat"]], np.r_[-90, stops["lon"]]
    D = np.rint(road_distance_matrix(lat, lon, lat, lon, 1.2) * 1000).astype(np.int64)
    return DepotInstance("CONUS", "WH-T", 35, -90, stops, D, cap, n_veh, max_km * 1000, 60, 10)


@pytest.mark.parametrize("method", ["nearest_neighbor", "ortools_standard", "ortools_gls"])
def test_routing_methods_feasible(method):
    inst = _instance([1, 2, 3, 1, 2, 4, 1, 3])
    routes = nearest_neighbor(inst) if method == "nearest_neighbor" else ortools_solve(inst, method, 1)[0]
    f = route_feasibility(inst, routes, method)
    assert f["unserved_stops"] == 0 and f["stops_visited_more_than_once"] == 0 and f["capacity_violations"] == 0
    assert sorted(j for r in routes for j in r) == list(range(1, 9))  # each stop exactly once, depot excluded


def test_gls_not_worse_than_standard_on_toy():
    inst = _instance([1, 2, 3, 1, 2, 4, 1, 3, 2, 2, 1, 3], cap=6)
    d = lambda rs: sum(inst.dist_m[a, b] for r in rs for a, b in zip([0] + r, r + [0]))
    std = ortools_solve(inst, "ortools_standard", 2)[0]
    gls = ortools_solve(inst, "ortools_gls", 2)[0]
    assert d(gls) <= d(std)


def test_unreachable_stops_reported_as_unserved():
    inst = _instance([1, 1, 1], max_km=1)  # route limit 1 km: nothing reachable
    routes, _ = ortools_solve(inst, "ortools_gls", 1)
    f = route_feasibility(inst, routes, "ortools_gls")
    assert f["unserved_stops"] == 3


def test_depot_instances_split_large_stops_and_stay_in_network():
    prob = toy_problem(capacity=100)
    sol = solve_cflp(prob)
    al, wh = allocation_table(prob, sol.assign), warehouse_table(prob, sol.open, sol.assign)
    al.loc[0, "forecast_orders_per_week"] = 23  # needs splitting with capacity 10
    inst = build_depot_instances(al, wh, "CONUS", {"vehicle_capacity_packages": 10})
    allstops = pd.concat([i.stops for i in inst])
    assert (allstops["packages"] <= 10).all()
    assert set(allstops["zone_id"]) <= set(al["zone_id"])
    assert sum(i.stops["packages"].sum() for i in inst) == sum(
        round(g["forecast_orders_per_week"].sum()) for _, g in al.groupby("warehouse_id"))
