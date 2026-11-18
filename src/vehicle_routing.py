"""Phase 6: Capacitated Vehicle Routing (CVRP) per warehouse depot.

Model (per depot, vehicles k, nodes 0 = depot, 1..n = delivery stops)::

    min  sum_k sum_i sum_j d_ij x_ijk
    s.t. every stop is visited exactly once (or dropped at a large penalty and reported unserved)
         each route starts and ends at the depot
         sum of packages on route k <= vehicle capacity
         route length <= max_route_km; at most `vehicles_per_depot` routes

Planning view: one week of consolidated deliveries. Each demand-zone centroid with at least one
package this week is a stop. Packages = forecast orders (one package per order: the data has no
weights or volumes), apportioned to whole packages per depot with the largest-remainder method.
That preserves the expected total. A stop whose packages exceed vehicle capacity is split into
several stops at the same location (split delivery). Stops come only from zones allocated to
the depot, which itself belongs to one network. Routes therefore never cross between the
mainland and Puerto Rico.

Three algorithms run on identical inputs:
  * nearest_neighbor: sequential greedy construction, without improvement.
  * ortools_standard: PATH_CHEAPEST_ARC + greedy-descent local search (stops at the first local minimum).
  * ortools_gls: PATH_CHEAPEST_ARC + Guided Local Search metaheuristic under a time limit.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .config import load_config
from .distance_calculator import DISTANCE_METHOD_LABEL, road_distance_matrix

METHODS = ("nearest_neighbor", "ortools_standard", "ortools_gls")
DROP_PENALTY_M = 10_000_000  # metres-equivalent penalty per dropped stop (forces service when feasible)


def largest_remainder(values: np.ndarray, total: int | None = None) -> np.ndarray:
    """Integer apportionment that preserves round(sum(values)) (Hamilton / largest-remainder)."""
    values = np.asarray(values, float)
    total = int(round(values.sum())) if total is None else total
    base = np.floor(values).astype(int)
    rem = total - base.sum()
    if rem > 0:
        order = np.argsort(-(values - base), kind="stable")
        base[order[:rem]] += 1
    return base


@dataclass
class DepotInstance:
    network: str
    warehouse_id: str
    depot_lat: float
    depot_lon: float
    stops: pd.DataFrame           # stop_id, zone_id, lat, lon, packages
    dist_m: np.ndarray            # (n+1)x(n+1) integer metres, node 0 = depot
    capacity: int
    n_vehicles: int
    max_route_m: int
    speed_kmh: float
    service_min: float


def build_depot_instances(allocation: pd.DataFrame, warehouses: pd.DataFrame, network: str,
                          overrides: dict | None = None, demand_scale: float = 1.0) -> list[DepotInstance]:
    """Create one routing instance per open warehouse from the CFLP allocation."""
    rc = load_config()["routing"]
    nc = dict(rc["networks"][network]); nc.update(overrides or {})
    cap = int(nc["vehicle_capacity_packages"])
    out = []
    al = allocation[(allocation["network"] == network) & (allocation["warehouse_id"] != "UNSERVED")]
    wh = warehouses[(warehouses["network"] == network) & warehouses["is_open"]]
    for w in wh.itertuples():
        a = al[al["warehouse_id"] == w.warehouse_id].reset_index(drop=True)
        pk = largest_remainder(a["forecast_orders_per_week"].to_numpy() * rc["packages_per_order"] * demand_scale)
        rows = []
        for r, p in zip(a.itertuples(), pk):
            k = 0
            while p > 0:
                q = min(p, cap)
                rows.append({"stop_id": f"{r.zone_id}" + (f"#{k + 1}" if pk is not None and (p > cap or k) else ""),
                             "zone_id": r.zone_id, "lat": r.zone_lat, "lon": r.zone_lon, "packages": int(q)})
                p -= q; k += 1
        stops = pd.DataFrame(rows, columns=["stop_id", "zone_id", "lat", "lon", "packages"])
        lat = np.r_[w.centroid_lat, stops["lat"].to_numpy(float)]
        lon = np.r_[w.centroid_lon, stops["lon"].to_numpy(float)]
        dist = np.rint(road_distance_matrix(lat, lon, lat, lon) * 1000).astype(np.int64)
        out.append(DepotInstance(network, w.warehouse_id, w.centroid_lat, w.centroid_lon, stops, dist, cap,
                                 int(nc["vehicles_per_depot"]), int(nc["max_route_km"] * 1000), float(nc["speed_kmh"]),
                                 float(rc["service_time_min_per_stop"])))
    return out


def nearest_neighbor(inst: DepotInstance) -> list[list[int]]:
    """Sequential nearest-neighbour: from the current node go to the closest unvisited stop that still
    fits the vehicle. Return to the depot when none fits and start a new vehicle.
    Fleet size and route length are NOT enforced (the baseline is constructive only);
    violations are reported by ``route_feasibility``."""
    n = len(inst.stops)
    dem = inst.stops["packages"].to_numpy()
    unvisited = set(range(1, n + 1))
    routes = []
    while unvisited:
        load, cur, route = 0, 0, []
        while True:
            cand = [j for j in unvisited if load + dem[j - 1] <= inst.capacity]
            if not cand:
                break
            j = min(cand, key=lambda j: (inst.dist_m[cur, j], j))
            route.append(j); load += dem[j - 1]; unvisited.discard(j); cur = j
        if not route:  # a single stop larger than capacity cannot happen (stops are split), but guard
            j = min(unvisited); route = [j]; unvisited.discard(j)
        routes.append(route)
    return routes


def ortools_solve(inst: DepotInstance, method: str, time_limit_s: float | None = None) -> tuple[list[list[int]], dict]:
    """Solve with OR-Tools. method = 'ortools_standard' or 'ortools_gls'."""
    n = len(inst.stops)
    if n == 0:
        return [], {"status": "no_stops"}
    mgr = pywrapcp.RoutingIndexManager(n + 1, inst.n_vehicles, 0)
    rt = pywrapcp.RoutingModel(mgr)
    D = inst.dist_m
    dem = np.r_[0, inst.stops["packages"].to_numpy()]
    cb = rt.RegisterTransitCallback(lambda a, b: int(D[mgr.IndexToNode(a), mgr.IndexToNode(b)]))
    rt.SetArcCostEvaluatorOfAllVehicles(cb)
    dcb = rt.RegisterUnaryTransitCallback(lambda a: int(dem[mgr.IndexToNode(a)]))
    rt.AddDimensionWithVehicleCapacity(dcb, 0, [inst.capacity] * inst.n_vehicles, True, "Capacity")
    rt.AddDimension(cb, 0, inst.max_route_m, True, "Distance")
    for node in range(1, n + 1):
        rt.AddDisjunction([mgr.NodeToIndex(node)], DROP_PENALTY_M)
    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    tl = time_limit_s or load_config()["routing"]["time_limit_s_per_depot"]
    if method == "ortools_gls":
        p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        p.time_limit.FromMilliseconds(int(tl * 1000))
    elif method == "ortools_standard":
        p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT
        p.time_limit.FromMilliseconds(int(tl * 1000))  # safety cap; greedy descent stops at its local minimum
    else:
        raise ValueError(method)
    sol = rt.SolveWithParameters(p)
    status = {0: "not_solved", 1: "success", 2: "fail", 3: "fail_timeout", 4: "invalid",
              5: "infeasible", 7: "optimal"}.get(rt.status(), str(rt.status()))
    if sol is None:
        return [], {"status": status}
    routes = []
    for v in range(inst.n_vehicles):
        idx = rt.Start(v); r = []
        while not rt.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            if node:
                r.append(node)
            idx = sol.Value(rt.NextVar(idx))
        if r:
            routes.append(r)
    return routes, {"status": status, "objective": sol.ObjectiveValue()}


def route_rows(inst: DepotInstance, routes: list[list[int]], method: str) -> pd.DataFrame:
    """Per-route metrics."""
    rc = load_config()["routing"]
    rows = []
    for k, r in enumerate(routes, start=1):
        seq = [0] + r + [0]
        dist_km = sum(inst.dist_m[a, b] for a, b in zip(seq[:-1], seq[1:])) / 1000
        pk = int(inst.stops["packages"].to_numpy()[np.array(r) - 1].sum())
        hours = dist_km / inst.speed_kmh + len(r) * inst.service_min / 60
        rows.append({"network": inst.network, "method": method, "warehouse_id": inst.warehouse_id,
                     "vehicle_id": f"{inst.warehouse_id}-V{k:02d}", "n_stops": len(r), "packages": pk,
                     "vehicle_capacity": inst.capacity, "utilization_pct": 100 * pk / inst.capacity,
                     "distance_km": dist_km, "duration_h": hours,
                     "route_cost": dist_km * rc["vehicle_cost_per_km"] + hours * rc["driver_cost_per_hour"],
                     "route_sequence": " > ".join([inst.warehouse_id] + [inst.stops["stop_id"].iat[j - 1] for j in r]
                                                  + [inst.warehouse_id]),
                     "distance_method": "haversine_circuity"})
    return pd.DataFrame(rows)


def stop_rows(inst: DepotInstance, routes: list[list[int]], method: str) -> pd.DataFrame:
    rows = []
    for k, r in enumerate(routes, start=1):
        prev, cum = 0, 0.0
        for pos, j in enumerate(r, start=1):
            cum += inst.dist_m[prev, j] / 1000
            s = inst.stops.iloc[j - 1]
            rows.append({"network": inst.network, "method": method, "warehouse_id": inst.warehouse_id,
                         "vehicle_id": f"{inst.warehouse_id}-V{k:02d}", "stop_sequence": pos, "stop_id": s["stop_id"],
                         "zone_id": s["zone_id"], "lat": s["lat"], "lon": s["lon"], "packages": int(s["packages"]),
                         "cumulative_km": cum, "depot_lat": inst.depot_lat, "depot_lon": inst.depot_lon})
            prev = j
    return pd.DataFrame(rows)


def route_feasibility(inst: DepotInstance, routes: list[list[int]], method: str) -> dict:
    """Independent check of every routing constraint."""
    n = len(inst.stops)
    visits = np.zeros(n + 1, int)
    for r in routes:
        for j in r:
            visits[j] += 1
    dem = inst.stops["packages"].to_numpy()
    loads = [dem[np.array(r) - 1].sum() for r in routes if r]
    lengths = [sum(inst.dist_m[a, b] for a, b in zip([0] + r, r + [0])) for r in routes]
    return {"network": inst.network, "method": method, "warehouse_id": inst.warehouse_id, "stops": n,
            "packages": int(dem.sum()), "routes": len(routes), "fleet_available": inst.n_vehicles,
            "unserved_stops": int((visits[1:] == 0).sum()),
            "unserved_packages": int(dem[visits[1:] == 0].sum()),
            "stops_visited_more_than_once": int((visits[1:] > 1).sum()),
            "capacity_violations": int(sum(l > inst.capacity for l in loads)),
            "route_length_violations": int(sum(L > inst.max_route_m for L in lengths)),
            "fleet_violation": int(max(0, len(routes) - inst.n_vehicles)),
            "all_routes_start_end_at_depot": True,  # by construction: sequences are depot + stops + depot
            "feasible": bool((visits[1:] == 1).all() and not any(l > inst.capacity for l in loads)
                             and not any(L > inst.max_route_m for L in lengths) and len(routes) <= inst.n_vehicles)}


def solve_network_routing(instances: list[DepotInstance], methods=METHODS, time_limit_s: float | None = None):
    """Run every method on every depot. Returns (routes_df, stops_df, feasibility_df, runtime_df)."""
    R, S, F, T = [], [], [], []
    for inst in instances:
        for m in methods:
            t0 = time.perf_counter()
            if m == "nearest_neighbor":
                routes, info = nearest_neighbor(inst), {"status": "constructed"}
            else:
                routes, info = ortools_solve(inst, m, time_limit_s)
            rt = time.perf_counter() - t0
            R.append(route_rows(inst, routes, m)); S.append(stop_rows(inst, routes, m))
            F.append({**route_feasibility(inst, routes, m), "solver_status": info.get("status")})
            T.append({"network": inst.network, "warehouse_id": inst.warehouse_id, "method": m, "runtime_s": rt})
    cat = lambda xs: pd.concat([x for x in xs if len(x)], ignore_index=True) if any(len(x) for x in xs) else pd.DataFrame()
    return cat(R), cat(S), pd.DataFrame(F), pd.DataFrame(T)


def summarize_routing(routes: pd.DataFrame, feas: pd.DataFrame, runtimes: pd.DataFrame) -> pd.DataFrame:
    """Network x method comparison table."""
    g = routes.groupby(["network", "method"]).agg(
        vehicles=("vehicle_id", "nunique"), total_distance_km=("distance_km", "sum"),
        total_duration_h=("duration_h", "sum"), total_route_cost=("route_cost", "sum"),
        packages=("packages", "sum"), mean_utilization_pct=("utilization_pct", "mean"),
        capacity_used=("packages", "sum"), capacity_available=("vehicle_capacity", "sum"))
    g["fleet_utilization_pct"] = 100 * g["capacity_used"] / g["capacity_available"]
    f = feas.groupby(["network", "method"]).agg(
        capacity_violations=("capacity_violations", "sum"), route_length_violations=("route_length_violations", "sum"),
        fleet_violations=("fleet_violation", "sum"), unserved_stops=("unserved_stops", "sum"),
        unserved_packages=("unserved_packages", "sum"), all_feasible=("feasible", "all"))
    t = runtimes.groupby(["network", "method"])["runtime_s"].sum()
    out = g.join(f).join(t).reset_index()
    out["distance_method"] = DISTANCE_METHOD_LABEL
    return out
