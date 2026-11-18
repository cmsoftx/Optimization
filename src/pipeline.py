"""Phase 7: integrated, configuration-driven optimisation pipeline.

Stages (each reads the files written by the previous one and validates them):
    warehouse  -> CFLP per network                      (Phase 4)
    genetic    -> GA + K-Means + random baselines         (Phase 5); selects the configuration for routing
    routing    -> CVRP per depot: NN / standard / GLS     (Phase 6)
    evaluate   -> experiments A-E, final summary, figures, reports (Phase 8 / 10)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .config import get_path, load_config
from .customer_allocation import allocation_table, summary_row, warehouse_table
from .warehouse_cflp import NETWORKS, build_problem, evaluate_configuration, solve_cflp, solver_report_row

log = logging.getLogger(__name__)


def out_dir() -> Path:
    return get_path("outputs_dir")


def read_output(name: str, required: list[str] | None = None) -> pd.DataFrame:
    """Read a pipeline output and validate its columns; explain which stage creates it if missing."""
    producers = {"selected_allocation.csv": "genetic", "selected_warehouses.csv": "genetic",
                 "customer_warehouse_allocation.csv": "warehouse", "optimal_warehouse_locations.csv": "warehouse",
                 "candidate_warehouses.csv": "warehouse", "vehicle_assignments.csv": "routing"}
    p = out_dir() / name
    if not p.exists():
        raise FileNotFoundError(f"{name} not found. Run `python main.py {producers.get(name, 'all')}` first.")
    df = pd.read_csv(p)
    missing = [c for c in (required or []) if c not in df.columns]
    if missing:
        raise KeyError(f"{name} is missing columns {missing}")
    return df


def save_run_config(stage: str, extra: dict | None = None) -> None:
    """Store the configuration used by a stage next to its outputs (reproducibility)."""
    d = out_dir() / "run_configs"
    d.mkdir(exist_ok=True)
    cfg = load_config()
    payload = {"stage": stage, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
               "optimization": cfg["optimization"], "genetic_algorithm": cfg["genetic_algorithm"],
               "routing": cfg["routing"], "experiments": cfg["experiments"], "seed": cfg["project"]["random_seed"],
               **(extra or {})}
    (d / f"{stage}.json").write_text(json.dumps(payload, indent=2, default=str))


# Phase 4
def run_warehouse() -> dict:
    out = out_dir()
    alloc, whs, summ, solv, cands = [], [], [], [], []
    results = {}
    for net in NETWORKS:
        prob = build_problem(net)
        sol = solve_cflp(prob)
        ev = evaluate_configuration(prob, sol.open, sol.assign, sol.unserved_fraction)
        if not ev["feasible"]:
            raise RuntimeError(f"CFLP {net} solution failed validation: {ev}")
        alloc.append(allocation_table(prob, sol.assign, "CFLP"))
        whs.append(warehouse_table(prob, sol.open, sol.assign, "CFLP"))
        summ.append(summary_row(prob, sol.open, sol.assign, sol.unserved_fraction, "CFLP (Pyomo + CBC)", sol.runtime_s,
                                termination=sol.termination, relative_gap=sol.gap))
        solv.append(solver_report_row(prob, sol))
        cands.append(prob.candidates.assign(network=net))
        results[net] = (prob, sol)
    wh = pd.concat(whs, ignore_index=True)
    wh[wh["is_open"]].to_csv(out / "optimal_warehouse_locations.csv", index=False)
    wh.to_csv(out / "warehouse_capacity_report.csv", index=False)
    pd.concat(alloc, ignore_index=True).to_csv(out / "customer_warehouse_allocation.csv", index=False)
    s = pd.DataFrame(summ)
    tot = s.select_dtypes("number").sum().to_dict()
    tot.update(network="ALL", method="CFLP (Pyomo + CBC)", feasible=bool(s["feasible"].all()))
    for k in ["avg_distance_km_order_weighted", "max_distance_km", "mean_utilization", "max_utilization", "relative_gap"]:
        tot[k] = np.nan
    s = pd.concat([s, pd.DataFrame([tot])], ignore_index=True)
    s["annual_total_cost"] = s["total_cost"] * load_config()["optimization"]["periods_per_year"]
    s.to_csv(out / "warehouse_optimization_results.csv", index=False)
    pd.DataFrame(solv).to_csv(out / "cflp_solver_report.csv", index=False)
    pd.concat(cands, ignore_index=True).to_csv(out / "candidate_warehouses.csv", index=False)
    save_run_config("warehouse")
    return results


# Phase 5
def run_genetic() -> dict:
    from .genetic_algorithm import kmeans_baseline, random_baseline, run_ga_experiment, search_space

    cfg = load_config()
    out = out_dir()
    seed = cfg["project"]["random_seed"]
    ga_rows, curves, comp, draws_all, sel_alloc, sel_wh = [], [], [], [], [], []
    for net in NETWORKS:
        prob = build_problem(net)
        cflp = solve_cflp(prob)
        ev_c = evaluate_configuration(prob, cflp.open, cflp.assign)
        ga_df, curve, best = run_ga_experiment(prob)
        ga_rows.append(ga_df); curves.append(curve)
        k = cflp.n_open
        km, km_rt = kmeans_baseline(prob, k, seed)
        draws, _ = random_baseline(prob, k, cfg["genetic_algorithm"]["random_baseline_draws"], seed)
        draws_all.append(draws)

        def row(method, ev, runtime, **kw):
            gap = 100 * (ev["total_cost"] - ev_c["total_cost"]) / ev_c["total_cost"]
            return {"network": net, "method": method, **ev, "runtime_s": runtime, "gap_vs_cflp_pct": gap, **kw}

        comp.append(row("CFLP (exact MILP)", ev_c, cflp.runtime_s, solver_termination=cflp.termination,
                        solver_relative_gap=cflp.gap))
        gb = best["eval"]
        comp.append(row("Genetic Algorithm (best of seeds)", gb, float(ga_df["runtime_s"].sum()),
                        ga_runs=len(ga_df), ga_total_cost_mean=ga_df["total_cost"].mean(),
                        ga_total_cost_std=ga_df["total_cost"].std(ddof=0),
                        ga_runs_matching_cflp=int((np.abs(ga_df["total_cost"] - ev_c["total_cost"]) < 1e-6).sum()),
                        search_space=search_space(prob)))
        comp.append(row(f"K-Means (k={k})", evaluate_configuration(prob, km.open, km.assign, km.unserved_fraction), km_rt))
        rmean = draws.mean(numeric_only=True).to_dict()
        rmean.update(network=net, feasible=bool(draws["feasible"].all()))
        comp.append(row(f"Random (k={k}, mean of {len(draws)})", {k_: rmean[k_] for k_ in ev_c}, float(draws["runtime_s"].sum()),
                        random_best_total=draws["total_cost"].min(), random_worst_total=draws["total_cost"].max(),
                        random_feasible_share=float(draws["feasible"].mean())))
        # configuration used downstream: lowest exact total cost (CFLP unless GA found better)
        if gb["total_cost"] < ev_c["total_cost"] - 1e-6:
            o, a, label = best["solution"].open, best["solution"].assign, "GA"
        else:
            o, a, label = cflp.open, cflp.assign, "CFLP"
        sel_alloc.append(allocation_table(prob, a, label)); sel_wh.append(warehouse_table(prob, o, a, label))
    pd.concat(ga_rows, ignore_index=True).to_csv(out / "genetic_algorithm_results.csv", index=False)
    pd.concat(curves, ignore_index=True).to_csv(out / "ga_convergence.csv", index=False)
    pd.DataFrame(comp).to_csv(out / "warehouse_algorithm_comparison.csv", index=False)
    pd.concat(draws_all, ignore_index=True).to_csv(out / "random_baseline_draws.csv", index=False)
    pd.concat(sel_alloc, ignore_index=True).to_csv(out / "selected_allocation.csv", index=False)
    pd.concat(sel_wh, ignore_index=True).to_csv(out / "selected_warehouses.csv", index=False)
    save_run_config("genetic")
    return {"comparison": pd.DataFrame(comp)}


# Phase 6
def selected_configuration() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        al = read_output("selected_allocation.csv", ["network", "zone_id", "warehouse_id", "forecast_orders_per_week"])
        wh = read_output("selected_warehouses.csv", ["network", "warehouse_id", "is_open", "centroid_lat", "centroid_lon"])
    except FileNotFoundError:
        log.warning("GA stage not run: routing uses the CFLP configuration")
        al = read_output("customer_warehouse_allocation.csv", ["network", "zone_id", "warehouse_id"])
        wh = read_output("warehouse_capacity_report.csv", ["network", "warehouse_id", "is_open"])
    return al, wh


def run_routing(time_limit_s: float | None = None, overrides: dict | None = None, demand_scale: float = 1.0,
                write: bool = True) -> dict:
    from .vehicle_routing import build_depot_instances, solve_network_routing, summarize_routing

    al, wh = selected_configuration()
    R, S, F, T = [], [], [], []
    for net in NETWORKS:
        inst = build_depot_instances(al, wh, net, (overrides or {}).get(net), demand_scale)
        r, s, f, t = solve_network_routing(inst, time_limit_s=time_limit_s)
        R.append(r); S.append(s); F.append(f); T.append(t)
    routes, stops, feas, rts = (pd.concat(x, ignore_index=True) for x in (R, S, F, T))
    comp = summarize_routing(routes, feas, rts)
    if write:
        out = out_dir()
        gls = "ortools_gls"
        stops[stops["method"] == gls].to_csv(out / "optimized_delivery_routes.csv", index=False)
        routes[routes["method"] == gls].to_csv(out / "vehicle_assignments.csv", index=False)
        routes.to_csv(out / "all_method_routes.csv", index=False)
        stops.to_csv(out / "all_method_route_stops.csv", index=False)
        comp.to_csv(out / "route_comparison.csv", index=False)
        dist = routes.groupby(["network", "warehouse_id", "method"]).agg(
            vehicles=("vehicle_id", "nunique"), stops=("n_stops", "sum"), packages=("packages", "sum"),
            distance_km=("distance_km", "sum"), duration_h=("duration_h", "sum"),
            longest_route_km=("distance_km", "max")).reset_index()
        dist.merge(rts, on=["network", "warehouse_id", "method"]).to_csv(out / "route_distance_report.csv", index=False)
        feas.to_csv(out / "route_feasibility_report.csv", index=False)
        save_run_config("routing", {"time_limit_s_per_depot": time_limit_s or load_config()["routing"]["time_limit_s_per_depot"]})
    return {"routes": routes, "stops": stops, "feasibility": feas, "comparison": comp}


# Phase 8 / 10
def make_optimization_figures() -> list:
    from . import optimization_visualization as V

    o = out_dir()
    rd = lambda n: pd.read_csv(o / n)
    figs = [V.fig_candidates(rd("cflp_zone_demand_forecast.csv"), rd("candidate_warehouses.csv")),
            V.fig_allocation(rd("customer_warehouse_allocation.csv"), rd("warehouse_capacity_report.csv")),
            V.fig_utilization(rd("warehouse_capacity_report.csv")),
            V.fig_cost_breakdown(rd("warehouse_optimization_results.csv")),
            V.fig_distance(rd("customer_warehouse_allocation.csv")),
            V.folium_allocation(rd("selected_allocation.csv"), rd("selected_warehouses.csv"), rd("candidate_warehouses.csv")),
            V.fig_ga_convergence(rd("ga_convergence.csv"), rd("warehouse_algorithm_comparison.csv")),
            V.fig_algorithm_comparison(rd("warehouse_algorithm_comparison.csv"))]
    R, S = rd("all_method_routes.csv"), rd("all_method_route_stops.csv")
    figs += [V.fig_routes_static(R, S, "CONUS", "phase6_routes_conus.png"),
             V.fig_routes_static(R, S, "Puerto Rico", "phase6_routes_puerto_rico.png"),
             V.folium_routes(S, R), V.fig_routing_comparison(rd("route_comparison.csv"))]
    for name, fn in [("forecast_impact_comparison.csv", V.fig_forecast_impact),
                     ("sensitivity_analysis.csv", V.fig_sensitivity),
                     ("sensitivity_analysis.csv", V.fig_sensitivity_routing),
                     ("robustness_analysis.csv", V.fig_robustness)]:
        if (o / name).exists():
            figs.append(fn(rd(name)))
    return figs


def run_evaluate(run_experiments: bool = True) -> dict:
    from . import experiments as E
    from .evaluation import consistency_checks, final_summary

    if run_experiments:
        E.experiment_a(); E.experiment_b(); E.experiment_c(); E.experiment_d(); E.experiment_e()
    else:
        E.experiment_a(); E.experiment_b()
    checks = consistency_checks()
    checks.to_csv(out_dir() / "consistency_checks.csv", index=False)
    if not checks["passed"].all():
        raise AssertionError("Consistency checks failed:\n" + checks[~checks["passed"]].to_string())
    summary = final_summary()
    figs = make_optimization_figures()
    save_run_config("evaluate")
    return {"checks": checks, "summary": summary, "figures": figs}
