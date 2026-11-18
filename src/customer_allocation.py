"""Phase 4/5: customer (demand-zone) to warehouse allocation.

* ``regret_allocation``: a fast capacity-feasible heuristic for the single-sourcing
  allocation subproblem (a generalised assignment problem). It is used inside the GA fitness.
  Zones are assigned in order of largest *regret* (second-best minus best cost) to their best
  open warehouse with enough remaining capacity. Shift moves then improve the result.
  It never violates capacity: a zone that fits nowhere is reported as unserved and penalised.
* Table builders turn a (problem, solution) pair into the Phase 4 output files.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .warehouse_cflp import NetworkProblem, evaluate_configuration


def regret_allocation(prob: NetworkProblem, open_mask: np.ndarray, max_passes: int = 20) -> tuple[np.ndarray, float]:
    """Capacity-feasible heuristic allocation. Returns (assign, transport_cost). assign = -1 means unserved."""
    open_idx = np.flatnonzero(open_mask)
    I = prob.n_zones
    assign = np.full(I, -1)
    if len(open_idx) == 0:
        return assign, 0.0
    C = prob.C[:, open_idx]
    rem = prob.capacity[open_idx].astype(float).copy()
    u = prob.units
    todo = np.ones(I, bool)
    big = 1e18
    while todo.any():
        fits = (u[:, None] <= rem[None, :] + 1e-9)
        cost = np.where(fits, C, big)
        cost[~todo] = big
        srt = np.sort(cost, axis=1)
        best = srt[:, 0]
        second = srt[:, 1] if cost.shape[1] > 1 else np.full(I, big)
        cand = todo & (best < big)
        if not cand.any():
            break  # remaining zones fit nowhere -> unserved
        regret = np.where(cand, np.minimum(second, big) - best, -1)
        regret[cand & (second >= big)] = big  # only one feasible option: assign first
        # tie-break deterministically by larger units, then index
        order = np.lexsort((np.arange(I), -u, -regret))
        i = order[0]
        k = int(np.argmin(cost[i]))
        assign[i] = open_idx[k]
        rem[k] -= u[i]
        todo[i] = False
    # local improvement: shift each zone to a cheaper warehouse with spare capacity
    load = np.zeros(prob.n_candidates)
    np.add.at(load, assign[assign >= 0], u[assign >= 0])
    for _ in range(max_passes):
        improved = False
        for i in np.flatnonzero(assign >= 0):
            cur = assign[i]
            for j in open_idx[np.argsort(prob.C[i, open_idx])]:
                if j == cur or prob.C[i, j] >= prob.C[i, cur] - 1e-12:
                    break
                if load[j] + u[i] <= prob.capacity[j] + 1e-9:
                    load[j] += u[i]; load[cur] -= u[i]; assign[i] = j; improved = True
                    break
        if not improved:
            break
    served = assign >= 0
    return assign, float(prob.C[np.flatnonzero(served), assign[served]].sum())


def allocation_table(prob: NetworkProblem, assign: np.ndarray, label: str = "selected") -> pd.DataFrame:
    z = prob.zones
    served = assign >= 0
    wh = prob.candidates.set_index(np.arange(prob.n_candidates))
    idx = np.where(served, assign, 0)
    dist = np.where(served, prob.dist_km[np.arange(prob.n_zones), idx], np.nan)
    return pd.DataFrame({
        "network": prob.network, "solution": label, "zone_id": z["zone_id"], "zone_city": z["dominant_city"],
        "zone_state": z["dominant_state"], "zone_lat": z["centroid_lat"], "zone_lon": z["centroid_lon"],
        "forecast_orders_per_week": prob.orders, "forecast_units_per_week": prob.units,
        "warehouse_id": np.where(served, wh["warehouse_id"].to_numpy()[idx], "UNSERVED"),
        "warehouse_city": np.where(served, wh["dominant_city"].to_numpy()[idx], ""),
        "warehouse_lat": np.where(served, wh["centroid_lat"].to_numpy()[idx], np.nan),
        "warehouse_lon": np.where(served, wh["centroid_lon"].to_numpy()[idx], np.nan),
        "road_km_approx": dist,
        "transport_cost_per_week": np.where(served, prob.C[np.arange(prob.n_zones), idx], 0.0),
    })


def warehouse_table(prob: NetworkProblem, open_mask: np.ndarray, assign: np.ndarray, label: str = "selected") -> pd.DataFrame:
    """One row per candidate: opened?, assigned zones/demand, capacity use."""
    served = assign >= 0
    load_u = np.bincount(assign[served], weights=prob.units[served], minlength=prob.n_candidates)
    load_o = np.bincount(assign[served], weights=prob.orders[served], minlength=prob.n_candidates)
    nz = np.bincount(assign[served], minlength=prob.n_candidates)
    tc = np.bincount(assign[served], weights=prob.C[np.flatnonzero(served), assign[served]], minlength=prob.n_candidates)
    c = prob.candidates.copy()
    c.insert(0, "network", prob.network)
    c["solution"] = label
    c["is_open"] = np.asarray(open_mask, bool)
    c["capacity_units_per_week"] = prob.capacity
    c["fixed_cost_per_week"] = np.where(c["is_open"], prob.fixed_cost, 0.0)
    c["assigned_zones"] = nz
    c["assigned_orders_per_week"] = load_o
    c["assigned_units_per_week"] = load_u
    c["unused_capacity_units"] = np.where(c["is_open"], prob.capacity - load_u, 0.0)
    c["utilization_pct"] = np.where(c["is_open"], 100 * load_u / prob.capacity, 0.0)
    c["transport_cost_per_week"] = tc
    c["high_demand_warehouse"] = c["is_open"] & (c["utilization_pct"] >= 85)
    return c


def summary_row(prob: NetworkProblem, open_mask, assign, unserved_fraction=None, method: str = "", runtime_s: float = 0.0,
                **extra) -> dict:
    ev = evaluate_configuration(prob, open_mask, assign, unserved_fraction)
    return {"network": prob.network, "method": method, **ev, "runtime_s": runtime_s, **extra}
