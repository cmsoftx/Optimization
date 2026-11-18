"""Phase 8: experiments A-E. Every number comes from an actual solver run."""
from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from .config import get_path, load_config
from .evaluation import pct_reduction
from .warehouse_cflp import NETWORKS, build_problem, evaluate_configuration, load_demand, solve_cflp

log = logging.getLogger(__name__)
OUT = get_path("outputs_dir")


# Experiment A: warehouse location methods
def experiment_a() -> pd.DataFrame:
    comp = pd.read_csv(OUT / "warehouse_algorithm_comparison.csv")
    rows = []
    for net, g in comp.groupby("network", sort=False):
        g = g.set_index("method")
        cflp = g.index[g.index.str.startswith("CFLP")][0]
        for m, r in g.iterrows():
            d = r.to_dict()
            for base in [b for b in g.index if b.startswith(("Random", "K-Means"))]:
                d[f"cost_reduction_vs_{base.split(' ')[0].lower()}_pct"] = pct_reduction(g.loc[base, "total_cost"], r["total_cost"])
            d["cost_reduction_of_cflp_vs_this_pct"] = pct_reduction(r["total_cost"], g.loc[cflp, "total_cost"])
            rows.append({"method": m, **d})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "experiment_warehouse_comparison.csv", index=False)
    return df


# Experiment B: routing methods
def experiment_b() -> pd.DataFrame:
    comp = pd.read_csv(OUT / "route_comparison.csv")
    rows = []
    for net, g in comp.groupby("network", sort=False):
        g = g.set_index("method")
        for m, r in g.iterrows():
            d = {"network": net, "method": m, **r.drop("network").to_dict()}
            for base in ["nearest_neighbor", "ortools_standard"]:
                d[f"distance_reduction_vs_{base}_pct"] = pct_reduction(g.loc[base, "total_distance_km"], r["total_distance_km"])
                d[f"time_reduction_vs_{base}_pct"] = pct_reduction(g.loc[base, "total_duration_h"], r["total_duration_h"])
                d[f"route_cost_reduction_vs_{base}_pct"] = pct_reduction(g.loc[base, "total_route_cost"], r["total_route_cost"])
            rows.append(d)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "experiment_routing_comparison.csv", index=False)
    return df


# Experiment C: does forecasting improve warehouse planning?
def _scenario_demand(pred: pd.DataFrame, model_by_net: dict, target: str) -> pd.Series:
    parts = []
    for net, (model, handling) in model_by_net.items():
        p = pred[(pred["network"] == net) & (pred["model"] == model) & (pred["handling"] == handling)]
        parts.append(p.groupby("zone_id")["predicted"].mean())
    return pd.concat(parts)


def forecast_impact_inputs() -> dict:
    """Back-test demand inputs on the Phase 3 post-break adapted window (13 held-out weeks).

    Both planners stand at the same origin (2017-10-28) with the same information:
      * Scenario 1, historical: each zone's historical average (all history to the origin).
      * Scenario 2, forecast: the model selected in Phase 3 per (target, network).
    The realised mean weekly demand over the 13 following weeks is the common evaluation scenario.
    """
    sel = pd.read_csv(OUT / "selected_forecast_model.csv")
    demand = load_demand()[["zone_id", "network", "centroid_lat", "centroid_lon", "dominant_city", "dominant_state"]]
    scen = {}
    for target, fname in [("orders", "order_demand_predictions.csv"), ("units", "unit_demand_predictions.csv")]:
        path = OUT / fname
        if not path.exists():
            raise FileNotFoundError(f"{fname} not found. Run `python main.py forecast` first.")
        p = pd.read_csv(path)
        p = p[(p["granularity"] == "W") & (p["eval_set"] == "post_break_adapted")]
        s = sel[sel["target"] == target]
        fc_models = {r.network: (r.model, r.handling) for r in s.itertuples()}
        hist_models = {net: ("historical_average", "none") for net in fc_models}
        actual = p[(p["model"] == "historical_average") & (p["handling"] == "none")].groupby("zone_id")["actual"].mean()
        scen.setdefault("historical", {})[target] = _scenario_demand(p, hist_models, target)
        scen.setdefault("forecast", {})[target] = _scenario_demand(p, fc_models, target)
        scen.setdefault("realised", {})[target] = actual
    frames = {}
    for name, d in scen.items():
        f = demand.copy()
        f["orders"] = f["zone_id"].map(d["orders"]).astype(float)
        f["units"] = f["zone_id"].map(d["units"]).astype(float)
        if f[["orders", "units"]].isna().any().any():
            raise ValueError(f"scenario {name} has zones without demand")
        if name == "forecast":  # same coherence rule as the Phase 3 hand-off
            f["units"] = np.maximum(f["units"], f["orders"])
        frames[name] = f
    return frames


def experiment_c() -> pd.DataFrame:
    frames = forecast_impact_inputs()
    rows = []
    for net in NETWORKS:
        base = build_problem(net)
        cands = base.candidates
        real = build_problem(net, demand=frames["realised"], candidates=cands)
        oracle = solve_cflp(real, allow_unserved=True)
        oracle_cost = evaluate_configuration(real, oracle.open, oracle.assign, oracle.unserved_fraction)["total_cost"]
        for scen in ["historical", "forecast", "realised"]:
            plan_prob = build_problem(net, demand=frames[scen], candidates=cands)
            t0 = time.perf_counter()
            plan = solve_cflp(plan_prob, allow_unserved=True)
            rt = time.perf_counter() - t0
            planned = evaluate_configuration(plan_prob, plan.open, plan.assign, plan.unserved_fraction)
            fixed_alloc = evaluate_configuration(real, plan.open, plan.assign, plan.unserved_fraction)
            rec = solve_cflp(real, fixed_open=plan.open, allow_unserved=True)
            recourse = evaluate_configuration(real, rec.open, rec.assign, rec.unserved_fraction)
            rows.append({
                "network": net, "scenario": {"historical": "1: historical average demand",
                                             "forecast": "2: selected forecast demand",
                                             "realised": "oracle: realised demand (perfect information)"}[scen],
                "planned_orders_per_week": planned["orders_per_week"], "planned_units_per_week": planned["units_per_week"],
                "realised_orders_per_week": recourse["orders_per_week"], "realised_units_per_week": recourse["units_per_week"],
                "warehouses_opened": planned["n_open"],
                "open_warehouses": ";".join(cands["warehouse_id"][plan.open]),
                "planned_total_cost": planned["total_cost"], "planned_unserved_units": planned["unserved_units"],
                "realised_opening_cost": recourse["opening_cost"], "realised_transport_cost": recourse["transport_cost"],
                "realised_total_cost": recourse["total_cost"],
                "realised_mean_utilization": recourse["mean_utilization"],
                "realised_max_utilization": recourse["max_utilization"],
                "realised_unserved_units": recourse["unserved_units"],
                "capacity_violation_units_if_plan_kept": fixed_alloc["capacity_overload_units"],
                "transport_cost_if_plan_kept": fixed_alloc["transport_cost"],
                "regret_vs_oracle": recourse["total_cost"] - oracle_cost,
                "regret_vs_oracle_pct": 100 * (recourse["total_cost"] - oracle_cost) / oracle_cost,
                "plan_runtime_s": rt, "plan_solver_termination": plan.termination,
                "plan_relative_gap": plan.gap, "plan_proven_optimal": plan.termination == "optimal"})
    df = pd.DataFrame(rows)
    for net in NETWORKS:
        g = df[df["network"] == net].set_index("scenario")
        h, f = g.iloc[0], g.iloc[1]
        df.loc[df["network"] == net, "forecast_cost_reduction_vs_historical_pct"] = pct_reduction(
            h["realised_total_cost"], f["realised_total_cost"])
    df.to_csv(OUT / "forecast_impact_comparison.csv", index=False)
    return df


# Experiment D: sensitivity
def _cflp_point(net: str, parameter: str, value, overrides: dict, demand=None) -> dict:
    prob = build_problem(net, demand=demand, overrides=overrides)
    t0 = time.perf_counter()
    sol = solve_cflp(prob, allow_unserved=True)
    ev = evaluate_configuration(prob, sol.open, sol.assign, sol.unserved_fraction)
    return {"experiment": "warehouse", "network": net, "parameter": parameter, "value": value, **ev,
            "n_zones": prob.n_zones, "n_candidates": prob.n_candidates, "termination": sol.termination,
            "relative_gap": sol.gap, "runtime_s": time.perf_counter() - t0}


def zones_for_diameter(diameter_km: float, network: str = "CONUS") -> pd.DataFrame:
    """Rebuild demand zones at another diameter. Demand = post-break weekly average per zone, which is
    the regime-reset estimator selected in Phase 3 for Puerto Rico, applied uniformly so that all
    diameters (including the base 50 km) are compared on equal terms."""
    from .preprocessing import build_zones

    cfg = load_config()
    o = pd.read_csv(get_path("processed_dir") / "orders.csv", parse_dates=["order_date"],
                    usecols=["order_id", "order_date", "network", "latitude", "longitude", "units", "in_demand_set",
                             "customer_city", "customer_state"])
    o = o[o["in_demand_set"] & (o["network"] == network)]
    brk = pd.Timestamp(cfg["preprocessing"]["regime_break_date"])
    end = pd.Timestamp("2018-01-27")
    weeks = ((end - brk).days + 1) / 7
    pts = o.groupby(["latitude", "longitude"])["units"].sum().rename("weight").reset_index()
    z = build_zones(pts, diameter_km, "S")
    o = o.merge(z[["latitude", "longitude", "zone_id"]], on=["latitude", "longitude"])
    post = o[(o["order_date"] >= brk) & (o["order_date"] <= end)]
    w = o.groupby("zone_id")["units"].transform("sum")
    cen = o.assign(wl=o["latitude"] * o["units"], wo=o["longitude"] * o["units"]).groupby("zone_id")[["wl", "wo", "units"]].sum()
    dom = o.groupby("zone_id")[["customer_city", "customer_state"]].agg(lambda s: s.mode().iat[0])
    agg = post.groupby("zone_id").agg(orders=("order_id", "size"), units=("units", "sum")) / weeks
    df = pd.DataFrame({"zone_id": cen.index, "network": network, "centroid_lat": cen["wl"] / cen["units"],
                       "centroid_lon": cen["wo"] / cen["units"]}).set_index("zone_id")
    df = df.join(dom.rename(columns={"customer_city": "dominant_city", "customer_state": "dominant_state"}))
    df = df.join(agg).fillna({"orders": 0.0, "units": 0.0}).reset_index()
    df["units"] = np.maximum(df["units"], df["orders"])
    del w
    return df


def experiment_d(routing: bool = True) -> pd.DataFrame:
    cfg = load_config()
    s = cfg["experiments"]["sensitivity"]
    rows = []
    for net in NETWORKS:
        nc = cfg["optimization"]["networks"][net]
        for m in s["capacity_multipliers"]:
            rows.append(_cflp_point(net, "capacity_multiplier", m, {"capacity_units_per_week": nc["capacity_units_per_week"] * m}))
        for p in s["fixed_warehouse_counts"]:
            if p <= nc["max_warehouses"] or net == "CONUS":
                if p > build_problem(net).n_candidates:
                    continue
                rows.append(_cflp_point(net, "fixed_warehouse_count", p, {"min_warehouses": p, "max_warehouses": p}))
        for m in s["fixed_cost_multipliers"]:
            rows.append(_cflp_point(net, "fixed_cost_multiplier", m, {"fixed_cost_per_week": nc["fixed_cost_per_week"] * m}))
        for m in s["cost_per_km_multipliers"]:
            rows.append(_cflp_point(net, "cost_per_km_multiplier", m, {"cost_per_order_km": nc["cost_per_order_km"] * m}))
        for g in s["demand_growth"]:
            rows.append(_cflp_point(net, "demand_growth", g, {"demand_growth": g}))
    for dkm in s["zone_diameters_km"]:
        z = zones_for_diameter(dkm)
        rows.append(_cflp_point("CONUS", "zone_diameter_km", dkm, {}, demand=z))
    df = pd.DataFrame(rows)
    if routing:
        from .pipeline import run_routing
        rr = []
        tl = 3
        for net in NETWORKS:
            for vc in s["vehicle_capacities"]:
                rr.append(_route_point(net, "vehicle_capacity", vc, {net: {"vehicle_capacity_packages": vc}}, tl))
            for nv in s["vehicles_per_depot"]:
                rr.append(_route_point(net, "vehicles_per_depot", nv, {net: {"vehicles_per_depot": nv}}, tl))
        df = pd.concat([df, pd.DataFrame(rr)], ignore_index=True)
        del run_routing
    df.to_csv(OUT / "sensitivity_analysis.csv", index=False)
    return df


def _route_point(net, parameter, value, overrides, tl, demand_scale=1.0) -> dict:
    from .vehicle_routing import build_depot_instances, solve_network_routing, summarize_routing
    from .pipeline import selected_configuration

    al, wh = selected_configuration()
    inst = build_depot_instances(al, wh, net, overrides.get(net), demand_scale)
    t0 = time.perf_counter()
    r, s, f, t = solve_network_routing(inst, methods=("ortools_gls",), time_limit_s=tl)
    c = summarize_routing(r, f, t).iloc[0].to_dict()
    return {"experiment": "routing", "network": net, "parameter": parameter, "value": value,
            "vehicles": c["vehicles"], "total_distance_km": c["total_distance_km"], "total_duration_h": c["total_duration_h"],
            "total_route_cost": c["total_route_cost"], "fleet_utilization_pct": c["fleet_utilization_pct"],
            "capacity_violations": c["capacity_violations"], "unserved_packages": c["unserved_packages"],
            "feasible": bool(c["all_feasible"]), "runtime_s": time.perf_counter() - t0}


# Experiment E: robustness of the selected solution
def experiment_e() -> pd.DataFrame:
    from .pipeline import selected_configuration

    cfg = load_config()
    al, wh = selected_configuration()
    rows = []
    for net in NETWORKS:
        prob = build_problem(net)
        open_ids = set(wh[(wh["network"] == net) & wh["is_open"]]["warehouse_id"])
        open_mask = prob.candidates["warehouse_id"].isin(open_ids).to_numpy()
        a = al[al["network"] == net].set_index("zone_id")["warehouse_id"]
        id2idx = {w: k for k, w in enumerate(prob.candidates["warehouse_id"])}
        planned_assign = np.array([id2idx.get(a.get(z), -1) for z in prob.zones["zone_id"]])
        for d in cfg["experiments"]["robustness_demand_changes"]:
            p = prob.with_demand(prob.orders * (1 + d), prob.units * (1 + d))
            kept = evaluate_configuration(p, open_mask, planned_assign)
            rec = solve_cflp(p, fixed_open=open_mask, allow_unserved=True)
            ev = evaluate_configuration(p, rec.open, rec.assign, rec.unserved_fraction)
            rt = _route_point(net, "demand_change", d, {}, 3, demand_scale=1 + d)
            rows.append({"network": net, "demand_change": d, "orders_per_week": ev["orders_per_week"],
                         "units_per_week": ev["units_per_week"], "warehouses": int(open_mask.sum()),
                         "capacity_overload_if_allocation_kept": kept["capacity_overload_units"],
                         "max_utilization_if_allocation_kept": kept["max_utilization"],
                         "reallocated_total_cost": ev["total_cost"], "reallocated_transport_cost": ev["transport_cost"],
                         "reallocated_max_utilization": ev["max_utilization"], "unserved_units": ev["unserved_units"],
                         "warehouse_plan_feasible": ev["feasible"],
                         "route_vehicles": rt["vehicles"], "route_distance_km": rt["total_distance_km"],
                         "route_cost": rt["total_route_cost"], "route_unserved_packages": rt["unserved_packages"],
                         "route_feasible": rt["feasible"],
                         "total_operating_cost": ev["total_cost"] + rt["total_route_cost"]})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "robustness_analysis.csv", index=False)
    return df
