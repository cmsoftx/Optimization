"""Phase 5: Genetic Algorithm (DEAP) for warehouse selection, plus K-Means and random baselines.

Encoding: one gene per candidate warehouse (1 = open). Fitness (minimised) uses the same data,
costs and capacities as the CFLP::

    f(y) = sum_j F_j y_j + transport(allocation(y)) + M * unserved_units(y) + M * |p(y) out of bounds|

where allocation(y) is the capacity-feasible regret heuristic of ``customer_allocation``.
The best chromosome of every run is re-evaluated with the *exact* allocation subproblem
(CBC with Y fixed), so reported GA costs are directly comparable with the CFLP optimum.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from deap import base, creator, tools
from sklearn.cluster import KMeans

from .config import load_config
from .customer_allocation import regret_allocation
from .warehouse_cflp import NetworkProblem, evaluate_configuration, solve_cflp

if not hasattr(creator, "FitnessMin"):
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
if not hasattr(creator, "Individual"):
    creator.create("Individual", list, fitness=creator.FitnessMin)


def _bounds(prob: NetworkProblem) -> tuple[int, int]:
    lo = min(prob.min_feasible_warehouses(), prob.max_warehouses)
    return lo, prob.max_warehouses


def repair(ind: list, prob: NetworkProblem, rng: random.Random) -> list:
    """Force the number of open warehouses into [p_lo, p_max] by random closing / opening."""
    lo, hi = _bounds(prob)
    on = [k for k, g in enumerate(ind) if g]
    off = [k for k, g in enumerate(ind) if not g]
    while len(on) > hi:
        k = on.pop(rng.randrange(len(on))); ind[k] = 0; off.append(k)
    while len(on) < lo and off:
        k = off.pop(rng.randrange(len(off))); ind[k] = 1; on.append(k)
    return ind


def fitness(ind, prob: NetworkProblem, cache: dict) -> tuple[float]:
    key = tuple(ind)
    if key not in cache:
        y = np.array(ind, bool)
        pen = load_config()["optimization"]["solver"]["unserved_penalty_per_unit"]
        assign, transport = regret_allocation(prob, y)
        unserved = float(prob.units[assign < 0].sum())
        lo, hi = prob.min_warehouses, prob.max_warehouses
        bound_violation = max(0, lo - y.sum()) + max(0, y.sum() - hi)
        cache[key] = float(prob.fixed_cost[y].sum() + transport + pen * unserved + pen * 100 * bound_violation)
    return (cache[key],)


@dataclass
class GARun:
    seed: int
    best_open: np.ndarray
    best_heuristic_cost: float
    history: pd.DataFrame
    runtime_s: float
    evaluations: int
    unique_evaluations: int
    generations_run: int


def run_ga(prob: NetworkProblem, seed: int, params: dict | None = None) -> GARun:
    """One GA run: tournament selection, two-point crossover, bit-flip mutation, repair, elitism."""
    gp = dict(load_config()["genetic_algorithm"]); gp.update(params or {})
    rng = random.Random(seed)
    random.seed(seed)  # DEAP operators use the global `random`
    n = prob.n_candidates
    indpb = gp["gene_flip_probability"] or 1.0 / n
    lo, hi = _bounds(prob)
    cache: dict = {}
    n_eval = 0
    tb = base.Toolbox()

    def init():
        k = rng.randint(lo, hi)
        genes = [0] * n
        for j in rng.sample(range(n), k):
            genes[j] = 1
        return creator.Individual(genes)

    tb.register("population", tools.initRepeat, list, init)
    tb.register("mate", tools.cxTwoPoint)
    tb.register("mutate", tools.mutFlipBit, indpb=indpb)
    tb.register("select", tools.selTournament, tournsize=gp["tournament_size"])

    def evaluate(pop):
        nonlocal n_eval
        for ind in pop:
            if not ind.fitness.valid:
                ind.fitness.values = fitness(ind, prob, cache); n_eval += 1

    t0 = time.perf_counter()
    pop = tb.population(n=gp["population_size"])
    evaluate(pop)
    hist, best_so_far, stall = [], float("inf"), 0
    gen = 0
    for gen in range(1, gp["generations"] + 1):
        elite = [tb.clone(i) for i in tools.selBest(pop, gp["elite_size"])]
        off = [tb.clone(i) for i in tb.select(pop, len(pop) - gp["elite_size"])]
        for a, b in zip(off[::2], off[1::2]):
            if rng.random() < gp["crossover_probability"]:
                tb.mate(a, b); del a.fitness.values, b.fitness.values
        for m in off:
            if rng.random() < gp["mutation_probability"]:
                tb.mutate(m); del m.fitness.values
        for m in off:
            before = list(m)
            repair(m, prob, rng)
            if list(m) != before and m.fitness.valid:
                del m.fitness.values
        evaluate(off)
        pop = elite + off
        fits = np.array([i.fitness.values[0] for i in pop])
        best = fits.min()
        stall = 0 if best < best_so_far - 1e-9 else stall + 1
        best_so_far = min(best_so_far, best)
        hist.append({"generation": gen, "best": best, "mean": fits.mean(), "std": fits.std(),
                     "best_so_far": best_so_far, "evaluations": n_eval, "unique_evaluations": len(cache),
                     "mean_open": float(np.mean([sum(i) for i in pop]))})
        if stall >= gp["patience"]:
            break
    best_ind = tools.selBest(pop, 1)[0]
    return GARun(seed, np.array(best_ind, bool), best_ind.fitness.values[0], pd.DataFrame(hist),
                 time.perf_counter() - t0, n_eval, len(cache), gen)


def run_ga_experiment(prob: NetworkProblem, seeds=None, params: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Run the GA for several seeds and re-evaluate every best chromosome with the exact allocation."""
    seeds = seeds or load_config()["genetic_algorithm"]["seeds"]
    rows, curves, best = [], [], None
    for s in seeds:
        r = run_ga(prob, s, params)
        exact = solve_cflp(prob, fixed_open=r.best_open, allow_unserved=True)
        ev = evaluate_configuration(prob, exact.open, exact.assign, exact.unserved_fraction)
        rows.append({"network": prob.network, "seed": s, "n_open": int(r.best_open.sum()),
                     "open_warehouses": ";".join(prob.candidates["warehouse_id"][r.best_open]),
                     "ga_fitness_heuristic_allocation": r.best_heuristic_cost,
                     "total_cost_excl_handling_exact_allocation": ev["opening_cost"] + ev["transport_cost"],
                     **{k: ev[k] for k in ["opening_cost", "transport_cost", "handling_cost", "total_cost",
                                           "avg_distance_km_order_weighted", "mean_utilization", "max_utilization",
                                           "unserved_units", "feasible"]},
                     "runtime_s": r.runtime_s, "allocation_runtime_s": exact.runtime_s, "generations": r.generations_run,
                     "evaluations": r.evaluations, "unique_evaluations": r.unique_evaluations,
                     "search_space_size": f"2^{prob.n_candidates}"})
        curves.append(r.history.assign(network=prob.network, seed=s))
        if best is None or ev["total_cost"] < best["eval"]["total_cost"]:
            best = {"run": r, "solution": exact, "eval": ev}
    return pd.DataFrame(rows), pd.concat(curves, ignore_index=True), best


def kmeans_baseline(prob: NetworkProblem, k: int, seed: int):
    """Demand-weighted k-means centres snapped to the nearest candidate, then exact allocation."""
    lat, lon = np.radians(prob.zones["centroid_lat"]), np.radians(prob.zones["centroid_lon"])
    xyz = np.c_[np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    clat, clon = np.radians(prob.candidates["centroid_lat"]), np.radians(prob.candidates["centroid_lon"])
    cxyz = np.c_[np.cos(clat) * np.cos(clon), np.cos(clat) * np.sin(clon), np.sin(clat)]
    t0 = time.perf_counter()
    km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(xyz, sample_weight=prob.orders + 1e-6)
    open_mask = np.zeros(prob.n_candidates, bool)
    for c in km.cluster_centers_:
        d = ((cxyz - c) ** 2).sum(axis=1)
        d[open_mask] = np.inf  # two centres may snap to the same site: take the next closest
        open_mask[int(np.argmin(d))] = True
    sol = solve_cflp(prob, fixed_open=open_mask, allow_unserved=True, method="K-Means + exact allocation")
    return sol, time.perf_counter() - t0


def random_baseline(prob: NetworkProblem, k: int, draws: int, seed: int) -> tuple[pd.DataFrame, list]:
    """k random candidates per draw, exact allocation for each draw."""
    rng = np.random.default_rng(seed)
    rows, sols = [], []
    for d in range(draws):
        open_mask = np.zeros(prob.n_candidates, bool)
        open_mask[rng.choice(prob.n_candidates, size=k, replace=False)] = True
        t0 = time.perf_counter()
        sol = solve_cflp(prob, fixed_open=open_mask, allow_unserved=True, method="Random + exact allocation")
        ev = evaluate_configuration(prob, sol.open, sol.assign, sol.unserved_fraction)
        rows.append({"network": prob.network, "draw": d, **ev, "runtime_s": time.perf_counter() - t0})
        sols.append(sol)
    return pd.DataFrame(rows), sols


def search_space(prob: NetworkProblem) -> int:
    lo, hi = _bounds(prob)
    return sum(math.comb(prob.n_candidates, k) for k in range(lo, hi + 1))
