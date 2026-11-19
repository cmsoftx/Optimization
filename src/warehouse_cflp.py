"""Phase 4: Capacitated Facility Location Problem (single-sourcing CFLP).

Model (one independent instance per logistics network)::

    min  sum_j F_j Y_j + sum_i sum_j C_ij X_ij + h * sum_i u_i + M * sum_i u_i S_i
    s.t. sum_j X_ij + S_i = 1                    for all i   (assign every zone once)
         sum_i u_i X_ij <= Q_j Y_j               for all j   (capacity in UNITS/week)
         X_ij <= Y_j                             for all i,j (closed warehouses serve nobody)
         p_min <= sum_j Y_j <= p_max                         (business limit)
         X, Y binary; S_i in [0, 1] and fixed to 0 unless unserved demand is explicitly allowed

    C_ij = c_km * dist_ij * o_i                  (o_i = forecast ORDERS/week = deliveries)

Orders drive transport cost because each order is one delivery. Units drive capacity because
warehouses store and handle units. The constant handling term h * sum u_i does not affect the
optimum and is reported separately. Networks are separate models, so an assignment can never
cross between the mainland and Puerto Rico.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from sklearn.cluster import KMeans

from .config import PROJECT_ROOT, load_config
from .distance_calculator import DISTANCE_METHOD_LABEL, road_distance_matrix

log = logging.getLogger(__name__)
NETWORKS = ("CONUS", "Puerto Rico")
REQUIRED_DEMAND_COLUMNS = ["zone_id", "network", "centroid_lat", "centroid_lon", "dominant_city", "dominant_state"]


@dataclass
class NetworkProblem:
    """All data of one CFLP instance (arrays are aligned with ``zones`` rows / ``candidates`` rows)."""
    network: str
    zones: pd.DataFrame
    candidates: pd.DataFrame
    dist_km: np.ndarray            # I x J approximate road km
    orders: np.ndarray             # I, orders per week
    units: np.ndarray              # I, units per week
    capacity: np.ndarray           # J, units per week
    fixed_cost: np.ndarray         # J, USD per week
    cost_per_order_km: float
    handling_cost_per_unit: float
    min_warehouses: int
    max_warehouses: int
    params: dict = field(default_factory=dict)

    @property
    def C(self) -> np.ndarray:
        return self.cost_per_order_km * self.dist_km * self.orders[:, None]

    @property
    def n_zones(self) -> int:
        return len(self.zones)

    @property
    def n_candidates(self) -> int:
        return len(self.candidates)

    def min_feasible_warehouses(self) -> int:
        """Lower bound on open warehouses implied by capacity (uniform capacities assumed)."""
        return max(self.min_warehouses, math.ceil(self.units.sum() / self.capacity.max() - 1e-9))

    def with_demand(self, orders: np.ndarray, units: np.ndarray) -> "NetworkProblem":
        return replace(self, orders=np.asarray(orders, float), units=np.asarray(units, float))


@dataclass
class CFLPSolution:
    network: str
    open: np.ndarray               # bool J
    assign: np.ndarray             # int I, candidate index or -1 if unserved
    unserved_fraction: np.ndarray  # I
    status: str
    termination: str
    objective: float
    lower_bound: float
    gap: float
    runtime_s: float
    method: str = "CFLP (Pyomo + CBC)"
    n_variables: int = 0
    n_constraints: int = 0
    bound_note: str = ""

    @property
    def n_open(self) -> int:
        return int(self.open.sum())


def load_demand(path=None, demand_columns: dict | None = None) -> pd.DataFrame:
    """Read the Phase 3 hand-off file and validate the columns the optimisation needs."""
    cfg = load_config()["optimization"]
    path = PROJECT_ROOT / (path or cfg["demand_file"])
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python main.py forecast` first.")
    df = pd.read_csv(path)
    cols = demand_columns or cfg["demand_columns"]
    missing = [c for c in REQUIRED_DEMAND_COLUMNS + list(cols.values()) if c not in df.columns]
    if missing:
        raise KeyError(f"{path.name} is missing columns {missing}")
    out = df[REQUIRED_DEMAND_COLUMNS].copy()
    out["orders"] = df[cols["orders"]].astype(float)
    out["units"] = df[cols["units"]].astype(float)
    if (out[["orders", "units"]] < 0).any().any() or out[["orders", "units"]].isna().any().any():
        raise ValueError("Demand must be non-negative and complete")
    return out


def generate_candidates(zones: pd.DataFrame, n_clusters: int, n_top: int, seed: int) -> pd.DataFrame:
    """Reproducible candidate set = demand-weighted coverage sites + highest-demand zones.

    * Coverage: k-means on 3-D unit vectors of the zone centroids, weighted by forecast orders.
      Each cluster centre is snapped to the nearest zone centroid, so every candidate is a
      real demand-zone location spread across the demand geography.
    * Concentration: the ``n_top`` zones with the most forecast orders.
    The union is de-duplicated. Candidates are only *options*: the CFLP decides which open.
    """
    lat, lon = np.radians(zones["centroid_lat"].to_numpy()), np.radians(zones["centroid_lon"].to_numpy())
    xyz = np.c_[np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    n = len(zones)
    source: dict[int, set] = {}
    if n_clusters >= n:
        for i in range(n):
            source.setdefault(i, set()).add("coverage")
    else:
        w = zones["orders"].to_numpy() + 1e-6
        km = KMeans(n_clusters=n_clusters, n_init=10, random_state=seed).fit(xyz, sample_weight=w)
        for c in km.cluster_centers_:
            source.setdefault(int(np.argmin(((xyz - c) ** 2).sum(axis=1))), set()).add("coverage")
    for i in np.argsort(-zones["orders"].to_numpy(), kind="stable")[: min(n_top, n)]:
        source.setdefault(int(i), set()).add("demand")
    idx = sorted(source)
    cand = zones.iloc[idx][["zone_id", "centroid_lat", "centroid_lon", "dominant_city", "dominant_state"]].copy()
    cand["source"] = ["+".join(sorted(source[i])) for i in idx]
    code = "US" if zones["network"].iat[0] == "CONUS" else "PR"
    cand.insert(0, "warehouse_id", [f"WH-{code}-{k + 1:02d}" for k in range(len(cand))])
    return cand.reset_index(drop=True)


def build_problem(network: str, demand: pd.DataFrame | None = None, overrides: dict | None = None,
                  candidates: pd.DataFrame | None = None) -> NetworkProblem:
    """Assemble a CFLP instance from config (+ optional overrides for sensitivity / what-if runs).

    ``overrides`` keys: capacity_units_per_week, fixed_cost_per_week, cost_per_order_km,
    handling_cost_per_unit, min_warehouses, max_warehouses, demand_growth.
    """
    cfg = load_config()
    p = dict(cfg["optimization"]["networks"][network])
    p.update(overrides or {})
    d = load_demand() if demand is None else demand
    z = d[d["network"] == network].reset_index(drop=True)
    if z.empty:
        raise ValueError(f"No demand zones for network {network}")
    growth = float(p.get("demand_growth", 0.0))
    z = z.assign(orders=z["orders"] * (1 + growth), units=z["units"] * (1 + growth))
    if candidates is None:
        candidates = generate_candidates(z, p["candidates"]["coverage_clusters"], p["candidates"]["top_demand_zones"],
                                         cfg["project"]["random_seed"])
    dist = road_distance_matrix(z["centroid_lat"], z["centroid_lon"], candidates["centroid_lat"],
                                candidates["centroid_lon"])
    J = len(candidates)
    return NetworkProblem(
        network=network, zones=z, candidates=candidates, dist_km=dist,
        orders=z["orders"].to_numpy(float), units=z["units"].to_numpy(float),
        capacity=np.full(J, float(p["capacity_units_per_week"])), fixed_cost=np.full(J, float(p["fixed_cost_per_week"])),
        cost_per_order_km=float(p["cost_per_order_km"]), handling_cost_per_unit=float(p["handling_cost_per_unit"]),
        min_warehouses=int(p["min_warehouses"]), max_warehouses=min(int(p["max_warehouses"]), J), params=p)


def solve_cflp(prob: NetworkProblem, fixed_open: np.ndarray | None = None, allow_unserved: bool = False,
               time_limit_s: float | None = None, method: str | None = None) -> CFLPSolution:
    """Solve the single-sourcing CFLP with Pyomo + CBC.

    ``fixed_open`` fixes Y (this turns the model into the exact capacitated allocation subproblem).
    ``allow_unserved`` adds penalised slack S_i so that over-capacity instances stay solvable and
    report unserved demand explicitly. Without it, an infeasible instance raises ``RuntimeError``.
    """
    scfg = load_config()["optimization"]["solver"]
    time_limit_s = time_limit_s or scfg["time_limit_s"]
    I, J = range(prob.n_zones), range(prob.n_candidates)
    C = prob.C
    m = pyo.ConcreteModel()
    m.Y = pyo.Var(J, domain=pyo.Binary)
    m.X = pyo.Var(I, J, domain=pyo.Binary)
    m.S = pyo.Var(I, bounds=(0, 1))
    pen = scfg["unserved_penalty_per_unit"]
    m.obj = pyo.Objective(
        expr=sum(prob.fixed_cost[j] * m.Y[j] for j in J)
        + sum(C[i, j] * m.X[i, j] for i in I for j in J)
        + sum(pen * max(prob.units[i], 1e-3) * m.S[i] for i in I), sense=pyo.minimize)
    m.assign = pyo.Constraint(I, rule=lambda m, i: sum(m.X[i, j] for j in J) + m.S[i] == 1)
    m.cap = pyo.Constraint(J, rule=lambda m, j: sum(prob.units[i] * m.X[i, j] for i in I) <= prob.capacity[j] * m.Y[j])
    m.link = pyo.Constraint(I, J, rule=lambda m, i, j: m.X[i, j] <= m.Y[j])
    if fixed_open is None:
        m.pmin = pyo.Constraint(expr=sum(m.Y[j] for j in J) >= prob.min_warehouses)
        m.pmax = pyo.Constraint(expr=sum(m.Y[j] for j in J) <= prob.max_warehouses)
    else:
        for j in J:
            m.Y[j].fix(int(bool(fixed_open[j])))
    if not allow_unserved:
        for i in I:
            m.S[i].fix(0)
    solver = pyo.SolverFactory(scfg["name"])
    if not solver.available(exception_flag=False):
        solver = pyo.SolverFactory("appsi_highs")
    else:
        solver.options["seconds"] = time_limit_s
        solver.options["ratio"] = scfg["mip_rel_gap"]
    t0 = time.perf_counter()
    res = solver.solve(m, load_solutions=False)
    rt = time.perf_counter() - t0
    term = str(res.solver.termination_condition)
    status = str(res.solver.status)
    if term in ("infeasible", "infeasibleOrUnbounded", "unbounded") or (len(res.solution) == 0 and term != "optimal"):
        raise RuntimeError(f"CFLP {prob.network}: no feasible solution (termination={term}). "
                           "Increase capacity or max_warehouses, or allow unserved demand.")
    m.solutions.load_from(res)
    Y = np.array([round(pyo.value(m.Y[j])) for j in J], bool)
    Xv = np.array([[pyo.value(m.X[i, j]) for j in J] for i in I])
    S = np.array([pyo.value(m.S[i]) for i in I])
    assign = np.where(Xv.max(axis=1) > 0.5, Xv.argmax(axis=1), -1)
    obj = float(pyo.value(m.obj))
    lb = res.problem.lower_bound
    lb = float(lb) if lb is not None and np.isfinite(float(lb)) else float("nan")
    gap = (obj - lb) / abs(obj) if np.isfinite(lb) and obj else float("nan")
    note = ""
    if term == "optimal" and np.isfinite(gap) and gap > scfg["mip_rel_gap"] + 1e-9:
        # CBC proved optimality within `ratio`, but the bound Pyomo parsed from its log contradicts that
        # (observed when some zones can never fit any warehouse). Do not report a bound we cannot trust.
        note = f"CBC reports optimal; parsed lower bound {lb:.6g} inconsistent with ratio tolerance, not reported"
        lb, gap = float("nan"), float("nan")
    return CFLPSolution(prob.network, Y, assign, S, status, term, obj, lb, max(gap, 0.0) if np.isfinite(gap) else gap, rt,
                        method or ("Exact allocation (CBC, fixed warehouses)" if fixed_open is not None else "CFLP (Pyomo + CBC)"),
                        m.nvariables(), m.nconstraints(), note)


def evaluate_configuration(prob: NetworkProblem, open_mask: np.ndarray, assign: np.ndarray,
                           unserved_fraction: np.ndarray | None = None) -> dict:
    """Recompute every cost and capacity figure from raw data (independent of the solver objective)."""
    open_mask = np.asarray(open_mask, bool)
    assign = np.asarray(assign, int)
    served = assign >= 0
    unserved_fraction = np.zeros(prob.n_zones) if unserved_fraction is None else np.asarray(unserved_fraction)
    unserved_units = float((prob.units * np.where(served, unserved_fraction, 1.0)).sum())
    C = prob.C
    transport = float(C[np.arange(prob.n_zones)[served], assign[served]].sum())
    opening = float(prob.fixed_cost[open_mask].sum())
    handling = float(prob.handling_cost_per_unit * prob.units[served].sum())
    load = np.bincount(assign[served], weights=prob.units[served], minlength=prob.n_candidates)
    overload = np.maximum(load - prob.capacity, 0.0)
    d = prob.dist_km[np.arange(prob.n_zones)[served], assign[served]]
    w = prob.orders[served]
    util = load[open_mask] / prob.capacity[open_mask] if open_mask.any() else np.array([np.nan])
    closed_serving = int(((~open_mask)[assign[served]]).sum())
    return {
        "network": prob.network, "n_open": int(open_mask.sum()), "opening_cost": opening, "transport_cost": transport,
        "handling_cost": handling, "cflp_objective_excl_handling": opening + transport,
        "total_cost": opening + transport + handling,
        "avg_distance_km_order_weighted": float((d * w).sum() / w.sum()) if w.sum() > 0 else float("nan"),
        "max_distance_km": float(d.max()) if len(d) else float("nan"),
        "mean_utilization": float(np.nanmean(util)), "max_utilization": float(np.nanmax(util)),
        "capacity_overload_units": float(overload.sum()), "unserved_units": unserved_units,
        "unserved_zones": int((~served).sum()), "closed_warehouses_serving": closed_serving,
        "feasible": bool(overload.sum() <= 1e-6 and unserved_units <= 1e-6 and closed_serving == 0
                         and prob.min_warehouses <= open_mask.sum() <= prob.max_warehouses),
        "orders_per_week": float(prob.orders.sum()), "units_per_week": float(prob.units.sum()),
    }


def solve_all_networks(networks=NETWORKS, overrides: dict | None = None) -> dict:
    """Build and solve every network. Returns {network: (problem, solution)}."""
    out = {}
    for net in networks:
        prob = build_problem(net, overrides=(overrides or {}).get(net))
        sol = solve_cflp(prob)
        log.info("CFLP %s: %d open, obj=%.1f, %s in %.1fs", net, sol.n_open, sol.objective, sol.termination, sol.runtime_s)
        out[net] = (prob, sol)
    return out


def solver_report_row(prob: NetworkProblem, sol: CFLPSolution) -> dict:
    return {"network": prob.network, "method": sol.method, "solver": load_config()["optimization"]["solver"]["name"],
            "status": sol.status, "termination": sol.termination,
            "proven_optimal": sol.termination == "optimal", "bound_note": sol.bound_note,
            "objective_excl_handling": sol.objective, "lower_bound": sol.lower_bound, "relative_gap": sol.gap,
            "runtime_s": sol.runtime_s, "n_zones": prob.n_zones, "n_candidates": prob.n_candidates,
            "n_variables": sol.n_variables, "n_constraints": sol.n_constraints,
            "time_limit_s": load_config()["optimization"]["solver"]["time_limit_s"],
            "distance_method": DISTANCE_METHOD_LABEL}
