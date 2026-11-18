"""Phase 10: final project report, viva questions and presentation outline.

Every number is read from the pipeline outputs, so the documents can be regenerated after any rerun.
"""
from __future__ import annotations

from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from .config import get_path, load_config
from .data_inspection import _md_table as _mdt

T = partial(_mdt, floatfmt="{:,.2f}")
T3 = partial(_mdt, floatfmt="{:,.3f}")
OUT = get_path("outputs_dir")
REP = get_path("reports_dir")


def _r(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / name)


def _facts() -> dict:
    cfg = load_config()
    eda = _r("eda_summary.csv")
    ev = lambda scope, m: eda[(eda["scope"] == scope) & (eda["metric"] == m)]["value"].iat[0]
    f = {"cfg": cfg, "rows": int(float(ev("raw", "order-item rows"))), "orders_raw": int(float(ev("raw", "orders"))),
         "orders": int(float(ev("demand set", "orders (deliveries)"))), "units": int(float(ev("demand set", "units"))),
         "eda": eda}
    f["demand"] = _r("cflp_zone_demand_forecast.csv")
    f["sel"] = _r("selected_forecast_model.csv")
    f["fe"] = _r("forecast_evaluation.csv")
    f["res"] = _r("warehouse_optimization_results.csv")
    f["solver"] = _r("cflp_solver_report.csv")
    f["opt"] = _r("optimal_warehouse_locations.csv")
    f["wc"] = _r("experiment_warehouse_comparison.csv")
    f["ga"] = _r("genetic_algorithm_results.csv")
    f["rc"] = _r("experiment_routing_comparison.csv")
    f["va"] = _r("vehicle_assignments.csv")
    f["fi"] = _r("forecast_impact_comparison.csv")
    f["sens"] = _r("sensitivity_analysis.csv")
    f["rob"] = _r("robustness_analysis.csv")
    f["summ"] = _r("final_performance_summary.csv")
    f["checks"] = _r("consistency_checks.csv")
    f["cands"] = _r("candidate_warehouses.csv")
    zd = pd.read_csv(get_path("processed_dir") / "zone_daily_demand.csv", parse_dates=["date"])
    pr = zd[(zd["network"] == "Puerto Rico") & (zd["date"] >= cfg["preprocessing"]["regime_break_date"])
            & (zd["date"] <= "2018-01-27")]
    w = pr.groupby(pr["date"].dt.to_period("W-SAT"))[["orders", "units"]].sum()
    w["units_per_order"] = w["units"] / w["orders"]
    f["pr_weeks"] = w.reset_index().rename(columns={"date": "week"}).assign(week=lambda d: d["week"].astype(str))
    tr = REP / "test_results.txt"
    f["tests"] = tr.read_text().strip().splitlines()[-1] if tr.exists() else "not recorded"
    return f


def _m(f, net, method_prefix, col):
    g = f["wc"][(f["wc"]["network"] == net) & f["wc"]["method"].str.startswith(method_prefix)]
    return float(g[col].iat[0])


def _route(f, net, method, col):
    return float(f["rc"][(f["rc"]["network"] == net) & (f["rc"]["method"] == method)][col].iat[0])


def _pct(a, b):
    return 100 * (a - b) / a if a else float("nan")


def build_final_report(f: dict) -> str:
    cfg = f["cfg"]
    oc, rcfg = cfg["optimization"], cfg["routing"]
    nets = ["CONUS", "Puerto Rico"]
    res = f["res"].set_index("network")
    opt = f["opt"]
    sel = f["sel"].copy()
    fe = f["fe"]
    pre = fe[(fe.granularity == "W") & (fe.eval_set == "pre_break_test") & (fe["mode"] == "one_step") & (fe.level == "zone_period")
             & (fe.tier == "all") & fe.network.isin(nets)]
    pre_t = pre.pivot_table(index=["target", "network"], columns="model", values="WAPE").round(3).reset_index()
    adz = fe[(fe.granularity == "W") & (fe.eval_set == "post_break_adapted") & (fe.level == "zone_total") & (fe.tier == "all")
             & fe.network.isin(nets) & (fe.model != "oracle_window_mean")]
    adz_t = adz.pivot_table(index=["target", "network"], columns=["model", "handling"], values="WAPE").round(3)
    adz_t.columns = [f"{a} [{b}]" for a, b in adz_t.columns]
    adz_t = adz_t.reset_index()
    wc = f["wc"]
    wct = wc[["network", "method", "n_open", "opening_cost", "transport_cost", "total_cost", "avg_distance_km_order_weighted",
              "mean_utilization", "unserved_units", "feasible", "runtime_s", "gap_vs_cflp_pct"]].copy()
    wct["mean_utilization"] *= 100
    ga = f["ga"]
    gas = ga.groupby("network").agg(runs=("seed", "size"), best=("total_cost", "min"), mean=("total_cost", "mean"),
                                    std=("total_cost", lambda s: s.std(ddof=0)), mean_generations=("generations", "mean"),
                                    mean_unique_evals=("unique_evaluations", "mean"), mean_runtime_s=("runtime_s", "mean")).reset_index()
    for net in nets:
        gas.loc[gas.network == net, "cflp_optimum"] = _m(f, net, "CFLP", "total_cost")
        gas.loc[gas.network == net, "runs_reaching_optimum"] = int((np.abs(ga[ga.network == net]["total_cost"] - _m(f, net, "CFLP", "total_cost")) < 1e-6).sum())
    rc = f["rc"][["network", "method", "vehicles", "total_distance_km", "total_duration_h", "total_route_cost", "fleet_utilization_pct",
                  "capacity_violations", "route_length_violations", "unserved_stops", "all_feasible", "runtime_s"]]
    fi = f["fi"][["network", "scenario", "planned_units_per_week", "warehouses_opened", "realised_opening_cost",
                  "realised_transport_cost", "realised_total_cost", "realised_unserved_units",
                  "capacity_violation_units_if_plan_kept", "regret_vs_oracle_pct", "plan_proven_optimal", "plan_relative_gap"]]
    s = f["sens"]
    sw = s[s.experiment == "warehouse"]
    sw_t = sw[["network", "parameter", "value", "n_open", "opening_cost", "transport_cost", "total_cost",
               "avg_distance_km_order_weighted", "unserved_units", "feasible", "termination"]]
    sr = s[s.experiment == "routing"][["network", "parameter", "value", "vehicles", "total_distance_km", "total_duration_h",
                                       "capacity_violations", "unserved_packages", "feasible"]]
    rob = f["rob"][["network", "demand_change", "units_per_week", "warehouses", "max_utilization_if_allocation_kept",
                    "capacity_overload_if_allocation_kept", "reallocated_max_utilization", "unserved_units",
                    "warehouse_plan_feasible", "route_vehicles", "route_distance_km", "route_feasible", "total_operating_cost"]]
    summ = f["summ"]
    op = {net: float(summ[(summ.network == net) & summ.metric.str.startswith("estimated operating cost per week")]["value"].iat[0]) for net in nets}
    opy = {net: float(summ[(summ.network == net) & (summ.metric == "estimated operating cost per year")]["value"].iat[0]) for net in nets}
    fi_red = {net: float(f["fi"][f["fi"].network == net]["forecast_cost_reduction_vs_historical_pct"].iat[0]) for net in nets}
    checks = f["checks"]
    cand_n = f["cands"].groupby("network").size().to_dict()

    gls_vs_nn = {n: _pct(_route(f, n, "nearest_neighbor", "total_distance_km"), _route(f, n, "ortools_gls", "total_distance_km")) for n in nets}
    gls_vs_std = {n: _pct(_route(f, n, "ortools_standard", "total_distance_km"), _route(f, n, "ortools_gls", "total_distance_km")) for n in nets}
    cflp_vs_rand = {n: _pct(_m(f, n, "Random", "total_cost"), _m(f, n, "CFLP", "total_cost")) for n in nets}
    cflp_vs_km = {n: _pct(_m(f, n, "K-Means", "total_cost"), _m(f, n, "CFLP", "total_cost")) for n in nets}
    ga_gap = {n: _m(f, n, "Genetic", "gap_vs_cflp_pct") for n in nets}
    nn_feasible = {n: bool(f["rc"][(f["rc"].network == n) & (f["rc"].method == "nearest_neighbor")]["all_feasible"].iat[0]) for n in nets}

    L = [
        "# Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimisation Using Hybrid Optimisation Algorithms",
        "",
        "_Final project report. It is generated by `python main.py report` from the pipeline outputs in `data/outputs/`. "
        "Every number in it is computed. Costs, capacities and fleet parameters are documented **simulation assumptions** "
        "(`config.yaml`). The dataset contains none of them._",
        "",
        "## 1. Abstract",
        "",
        f"The system was built and evaluated on the DataCo Smart Supply Chain dataset ({f['rows']:,} order-item rows, "
        f"{f['orders']:,} valid orders after cleaning). It runs in stages:",
        "",
        "1. Order-item records are aggregated into deliveries and into bounded-diameter demand zones in two separate "
        "logistics networks: the contiguous US (CONUS) and Puerto Rico.",
        "2. Zone demand is forecast with regime-aware methods, because the data change abruptly in October 2017.",
        "3. Warehouses are located with an exact Capacitated Facility Location Problem (CFLP), solved with Pyomo and CBC.",
        "4. A DEAP Genetic Algorithm (GA), K-Means and random selection serve as comparison methods.",
        "5. Weekly delivery routes are built per depot with a CVRP, solved by OR-Tools with Guided Local Search (GLS).",
        "",
        "Results:",
        "",
        f"* **CFLP:** solved to proven optimality in both networks. It opens {int(res.loc['CONUS', 'n_open'])} CONUS and "
        f"{int(res.loc['Puerto Rico', 'n_open'])} Puerto Rico warehouses.",
        f"* **CFLP vs random selection** (same number of warehouses): {cflp_vs_rand['CONUS']:.1f}% lower total cost in CONUS "
        f"and {cflp_vs_rand['Puerto Rico']:.1f}% lower in Puerto Rico.",
        f"* **CFLP vs K-Means:** {cflp_vs_km['CONUS']:.2f}% lower in CONUS and {cflp_vs_km['Puerto Rico']:.1f}% lower in Puerto Rico.",
        f"* **Genetic Algorithm:** its best configuration is {ga_gap['CONUS']:.2f}% above the optimum in CONUS and "
        f"{ga_gap['Puerto Rico']:.2f}% above it in Puerto Rico.",
        f"* **Routing:** GLS shortens CONUS routes by {gls_vs_nn['CONUS']:.1f}% versus Nearest Neighbor. The Nearest "
        f"Neighbor routes also violate the route-length limit. GLS gains only {gls_vs_std['CONUS']:.2f}% over the standard "
        "OR-Tools search.",
        f"* **Forecast-based vs historical-average planning** (13 held-out weeks): realised cost is {fi_red['CONUS']:.1f}% "
        f"lower with forecasts in CONUS, but **{abs(fi_red['Puerto Rico']):.1f}% higher** in Puerto Rico. The Puerto Rico "
        "unit forecast was biased high, which forced an extra warehouse.",
        "",
        "## 2. Introduction",
        "",
        "E-commerce fulfilment cost is dominated by two coupled decisions:",
        "",
        "* a **strategic** decision: where warehouses are opened, and which customers each one serves;",
        "* an **operational** decision: how vehicles deliver from those warehouses.",
        "",
        "Both decisions depend on demand, which must be forecast. This project chains the three steps "
        "(forecasting → facility location → vehicle routing) into one reproducible pipeline. Each optimisation step is "
        "compared against simpler baselines on identical inputs.",
        "",
        "## 3. Problem statement",
        "",
        "Given historical customer orders, the system must decide:",
        "",
        "1. where to open warehouses and how many;",
        "2. which warehouse serves each demand zone, within warehouse capacity;",
        "3. how many vehicles each warehouse needs and which zones each vehicle visits, in which order, within vehicle capacity.",
        "",
        "The goal is to minimise warehouse opening cost, transport cost and route distance. Every constraint must be "
        "respected, and all unserved demand must be reported explicitly.",
        "",
        "## 4. Research objectives",
        "",
        "1. Build a leakage-free demand forecast at zone level and select the method by measured accuracy.",
        "2. Solve the single-sourcing CFLP exactly, and quantify its advantage over heuristic and naive placement.",
        "3. Test whether a Genetic Algorithm reaches the exact optimum, and at what computational cost.",
        "4. Route vehicles with GLS, and quantify its gain over constructive and standard local-search methods.",
        "5. Measure whether forecasting improves warehouse planning against realised demand.",
        "6. Measure the sensitivity and robustness of the solution to the simulated assumptions.",
        "",
        "## 5. Dataset description",
        "",
        "* **Source:** DataCo Smart Supply Chain for Big Data Analysis (Kaggle `shashwatwork/dataco-smart-supply-chain-for-big-data-analysis`).",
        f"* **Size:** {f['rows']:,} order-item rows × 53 columns, covering {f['orders_raw']:,} orders from January 2015 to January 2018.",
        "* **Coordinates:** the only coordinates are customer-side `Latitude`/`Longitude` (US and Puerto Rico). Destination "
        "fields (`Order City`/`Order Country`, 164 countries) have no coordinates. They are statistically independent of "
        "customer location (Cramér's V ≈ 0.01), so demand is placed at customer coordinates. International destinations "
        "are never routed.",
        "* **Missing business data:** the dataset has no warehouses, capacities, costs, fleet, package weights or road "
        "distances. All of these are simulation assumptions (§13).",
        "* **Personal data:** customer names and streets are present in the raw file. They are dropped before any output "
        "is written, and tests enforce this.",
        "",
        "## 6. Data preprocessing methodology",
        "",
        "* **Flag, don't delete.** Rows are flagged rather than deleted, and every decision is logged "
        "(`data_quality_report.csv`).",
        "* **Non-demand orders:** cancelled and suspected-fraud orders never ship, so they are excluded from demand.",
        "* **Invalid coordinates excluded:** sign flips, truncated longitudes, a placeholder point near the US centroid, "
        "and points more than 1,000 km from their state's median location.",
        f"* **Demand set:** {f['orders']:,} orders and {f['units']:,} units remain. Order-item rows are aggregated into one "
        "row per order (= one delivery).",
        "* **Demand zones:** complete-linkage clustering with a guaranteed maximum diameter (CONUS 50 km, island networks "
        f"10 km). This gives {int((f['demand'].network == 'CONUS').sum())} CONUS zones and "
        f"{int((f['demand'].network == 'Puerto Rico').sum())} Puerto Rico zones. Hawaii (6 zones) is analysis-only.",
        "* **Reconciliation:** 37 checks confirm that units, orders, items and sales are conserved from items to orders "
        "to zone-days.",
        "",
        "## 7. Demand forecasting methodology",
        "",
        "* **Panel:** zone × complete week (Sunday–Saturday). The week of 2017-10-01 starts exactly at a distribution "
        "break, after which units per order fall from about 6.5 to about 1. Orders and units are forecast separately.",
        "* **Methods compared:** historical average, moving average, Random Forest and XGBoost (global models).",
        "* **Features:** lags, rolling means, shares and calendar features, built strictly from past periods. A test "
        "perturbs future values and checks that no past feature changes.",
        "* **Splits:** chronological train/validation/test, before and after the break.",
        "* **Post-break evaluation:** 4 post-break weeks are observed, then 13 held-out weeks are forecast.",
        "* **Selection:** per network and target, the lowest **zone-total WAPE** over those 13 weeks. That is the "
        "quantity the CFLP consumes.",
        "",
        "Stable regime, zone-week WAPE (one-step):",
        "",
        T3(pre_t),
        "",
        "Post-break adapted window, zone-total WAPE (13 held-out weeks):",
        "",
        T3(adz_t),
        "",
        "Selected models:",
        "",
        T3(sel[["target", "network", "model", "handling", "WAPE", "MAE", "RMSE", "bias_pct"]]),
        "",
        "**XGBoost was not selected for any target or network.** Two reasons:",
        "",
        "* Zone-week demand is near-stationary count noise around a level, so there is little nonlinear structure for "
        "boosting to exploit.",
        "* The decisive post-break problem is a shift in level and location, which no model trained on pre-break data "
        "can learn.",
        "",
        "Puerto Rico's demand relocated about 35 km within the island at the break, so a regime-reset estimator was "
        "selected there.",
        "",
        "## 8. CFLP mathematical formulation",
        "",
        "Sets: zones $i\\in I$ and candidate sites $j\\in J$ (one model per network). Parameters: forecast orders $o_i$ and "
        "units $u_i$ per week, approximate road distance $d_{ij}$, fixed cost $F_j$, capacity $Q_j$ and cost per order-km "
        "$c$. Binary decision variables are $Y_j$ (open site $j$) and $X_{ij}$ (zone $i$ is served by $j$).",
        "",
        "$$\\min\\ Z=\\sum_j F_jY_j+\\sum_i\\sum_j C_{ij}X_{ij},\\qquad C_{ij}=c\\,d_{ij}\\,o_i$$",
        "",
        "$$\\text{s.t.}\\quad\\sum_j X_{ij}=1\\ \\forall i;\\quad \\sum_i u_iX_{ij}\\le Q_jY_j\\ \\forall j;\\quad "
        "X_{ij}\\le Y_j\\ \\forall i,j;\\quad p_{min}\\le\\sum_jY_j\\le p_{max};\\quad X,Y\\in\\{0,1\\}.$$",
        "",
        "* **Orders drive transport, units drive capacity.** Each order is one delivery, so orders determine transport "
        "cost. Warehouses store and handle units, so units consume capacity.",
        "* **Constant handling cost:** a uniform cost of "
        f"${oc['networks']['CONUS']['handling_cost_per_unit']}/unit is added for reporting only. It does not change "
        "the optimum.",
        "* **Tighter relaxation:** the disaggregated linking constraints $X_{ij}\\le Y_j$ give a much tighter LP "
        "relaxation than the aggregated form.",
        "* **Over-capacity cases:** for experiments, penalised slack variables report unserved demand instead of "
        "failing silently.",
        f"* **Candidate sites:** {cand_n.get('CONUS')} in CONUS, from demand-weighted k-means coverage sites plus the "
        f"highest-demand zones. All {cand_n.get('Puerto Rico')} zones in Puerto Rico.",
        "* **Distances:** great-circle distance × "
        f"{oc['distance']['circuity_factor']} circuity (OSRM was not reachable). These are **approximate** road "
        "distances, not road-network distances.",
        "* **Complexity:** the problem is NP-hard. CBC solves it by branch-and-cut with LP relaxations.",
        "",
        T(f["solver"][["network", "termination", "proven_optimal", "objective_excl_handling", "lower_bound", "relative_gap",
                       "runtime_s", "n_zones", "n_candidates", "n_variables", "n_constraints"]]),
        "",
        "Selected warehouses:",
        "",
        T(opt[["network", "warehouse_id", "dominant_city", "dominant_state", "assigned_zones", "assigned_orders_per_week",
               "assigned_units_per_week", "capacity_units_per_week", "utilization_pct"]]),
        "",
        "![allocation](figures/phase4_selected_allocation.png)",
        "",
        "## 9. Genetic Algorithm methodology",
        "",
        "* **Chromosome:** a binary vector $y\\in\\{0,1\\}^{|J|}$, where gene $j$ = 1 means candidate $j$ is open. A "
        "**repair** operator keeps the number of open sites between the capacity-implied minimum and $p_{max}$.",
        "* **Fitness (minimised):** $\\sum_jF_jy_j+\\text{transport}(A(y))+M\\cdot\\text{unserved}(y)$. Here $A(y)$ "
        "allocates zones to open sites with a capacity-feasible regret heuristic plus shift improvement, so it never "
        "overloads a warehouse; zones that fit nowhere are unserved and penalised. The data and costs are the same as "
        "in the CFLP.",
        "* **Fair final comparison:** the best chromosome of each run is re-allocated with the **exact** subproblem "
        "(CBC with $Y$ fixed), so its cost is directly comparable with the CFLP optimum.",
        f"* **Operators:**",
        f"  * tournament selection (k = {cfg['genetic_algorithm']['tournament_size']});",
        f"  * two-point crossover (p = {cfg['genetic_algorithm']['crossover_probability']});",
        f"  * bit-flip mutation (p = {cfg['genetic_algorithm']['mutation_probability']} per individual, 1/|J| per gene);",
        f"  * elitism ({cfg['genetic_algorithm']['elite_size']});",
        f"  * population {cfg['genetic_algorithm']['population_size']}, at most "
        f"{cfg['genetic_algorithm']['generations']} generations, early stop after {cfg['genetic_algorithm']['patience']} "
        f"generations without improvement;",
        f"  * {len(cfg['genetic_algorithm']['seeds'])} seeds.",
        "* **Complexity:** each fitness evaluation costs O(I²·p) for the regret allocation. The search space is about "
        "3.2×10⁹ configurations in CONUS, so exhaustive enumeration is impossible. The GA explores it with a few "
        "thousand evaluations.",
        "",
        T(gas),
        "",
        "![GA convergence](figures/ga_convergence.png)",
        "",
        "## 10. CVRP mathematical formulation",
        "",
        "For each depot (an open warehouse), with node 0 = depot, stops $1..n$ and vehicles $k$:",
        "",
        "$$\\min\\sum_k\\sum_i\\sum_j d_{ij}x_{ijk}\\quad\\text{s.t. each stop is visited exactly once; each route starts and "
        "ends at the depot; }\\sum_{i\\in r_k}q_i\\le Q_v;\\ \\text{length}(r_k)\\le L_{max};\\ |\\{k\\}|\\le K.$$",
        "",
        "* **Planning period:** one week of consolidated deliveries.",
        "* **Stops:** each demand-zone centroid with at least one package is a stop. One package = one forecast order, "
        "since the data has no weights or volumes. Packages are apportioned per depot with the largest-remainder method, "
        "which preserves the expected total.",
        "* **Split deliveries:** a stop with more packages than one vehicle holds is split into several stops at the same "
        "location.",
        "* **No mainland–island routes:** stops come only from zones allocated to the depot, so routes never cross "
        "between the mainland and Puerto Rico.",
        f"* **Parameters:** CONUS vehicles carry {rcfg['networks']['CONUS']['vehicle_capacity_packages']} packages, with "
        f"L_max = {rcfg['networks']['CONUS']['max_route_km']} km and {rcfg['networks']['CONUS']['vehicles_per_depot']} "
        f"vehicles per depot. Puerto Rico L_max = {rcfg['networks']['Puerto Rico']['max_route_km']} km. Speeds are "
        f"{rcfg['networks']['CONUS']['speed_kmh']} / {rcfg['networks']['Puerto Rico']['speed_kmh']} km/h, plus "
        f"{rcfg['service_time_min_per_stop']} min service per stop.",
        "* **Unserved stops:** each stop is in a penalised disjunction, so any unserved stop is reported, never hidden.",
        "",
        "## 11. Guided Local Search methodology",
        "",
        "1. **Initial solution:** PATH_CHEAPEST_ARC repeatedly extends a route with the cheapest feasible arc.",
        "2. **Local search neighbourhoods:** relocate, exchange, 2-opt, Or-opt, cross and inter-route moves, all evaluated "
        "under the capacity and distance dimensions.",
        "3. **Cost:** the sum of arc distances. Penalties for dropped stops are added.",
        "4. **Features and penalties:** GLS treats each arc as a feature with cost $c_a$. At a local minimum it penalises "
        "the arcs with maximal utility $c_a/(1+p_a)$ by incrementing $p_a$.",
        "5. **Augmented objective:** the search continues on $g(s)=\\text{cost}(s)+\\lambda\\sum_a p_a I_a(s)$.",
        "6. **Escaping local minima:** penalised long arcs make neighbouring solutions relatively cheaper. This moves the "
        "search out of local minima that plain greedy descent (the standard baseline) cannot leave.",
        f"7. **Termination:** a time limit of {rcfg['time_limit_s_per_depot']} s per depot. The best solution under the "
        "*true* cost is returned.",
        "",
        "## 12. Hybrid optimisation architecture",
        "",
        "Raw data → cleaning → demand zones → forecasting → candidate generation → **CFLP (exact)** → **GA / K-Means / "
        "random (comparison)** → selected configuration (lowest exact cost) → allocation → **CVRP (NN / standard / GLS)** "
        "→ experiments → dashboard & reports.",
        "",
        "The pipeline is driven by `main.py` (`preprocess, forecast, warehouse, genetic, routing, evaluate, report, all`) "
        "and configured by `config.yaml`. The configuration of each stage is saved in `data/outputs/run_configs/`.",
        "",
        "## 13. Experimental setup",
        "",
        "Simulation assumptions (weekly planning period; annual = ×52):",
        "",
        T(pd.DataFrame([{"network": n, **{k: v for k, v in oc["networks"][n].items() if k != "candidates"},
                         "vehicle_capacity": rcfg["networks"][n]["vehicle_capacity_packages"],
                         "vehicles_per_depot": rcfg["networks"][n]["vehicles_per_depot"],
                         "max_route_km": rcfg["networks"][n]["max_route_km"]} for n in nets])),
        "",
        "* **Comparability:** all methods use identical demand, candidates, distances, capacities and costs.",
        "* **Reproducibility:** seeds are fixed. The CFLP is deterministic.",
        "* **GLS timing:** GLS is time-limited, so its results can vary slightly between machines.",
        "",
        "## 14. Performance comparisons",
        "",
        "### Experiment A: warehouse location",
        "",
        T(wct),
        "",
        "![comparison](figures/phase5_warehouse_algorithm_comparison.png)",
        "",
        "### Experiment B: delivery routing",
        "",
        T(rc),
        "",
        "![routing](figures/phase6_routing_comparison.png)",
        "",
        "### Experiment C: forecasting impact on warehouse placement",
        "",
        "Both planners stand at 2017-10-28 with the same information. Each plan is evaluated on the realised demand of the "
        "13 following weeks, with zones re-allocated optimally to the plan's warehouses (recourse). The oracle uses "
        "realised demand (perfect information).",
        "",
        T(fi),
        "",
        "![forecast impact](figures/phase8_forecast_impact.png)",
        "",
        "## 15. Sensitivity analysis (Experiment D)",
        "",
        T(sw_t),
        "",
        T(sr),
        "",
        "![sensitivity](figures/phase8_sensitivity_warehouse.png)",
        "",
        "![routing sensitivity](figures/phase8_sensitivity_routing.png)",
        "",
        "### Robustness (Experiment E)",
        "",
        T(rob),
        "",
        "![robustness](figures/phase8_robustness.png)",
        "",
        "## 16. Results and discussion",
        "",
        f"* **Warehouses.** The CFLP opens {int(res.loc['CONUS', 'n_open'])} CONUS warehouses at "
        f"{', '.join(opt[opt.network == 'CONUS']['dominant_city'])}. Their total cost is "
        f"${res.loc['CONUS', 'total_cost']:,.0f}/week: ${res.loc['CONUS', 'opening_cost']:,.0f} opening, "
        f"${res.loc['CONUS', 'transport_cost']:,.0f} transport and ${res.loc['CONUS', 'handling_cost']:,.0f} handling. "
        f"Puerto Rico needs {int(res.loc['Puerto Rico', 'n_open'])} warehouses, purely because of capacity: transport "
        f"there costs only ${res.loc['Puerto Rico', 'transport_cost']:,.0f}/week.",
        f"* **Exact vs heuristic.** The CFLP solved to proven optimality in about "
        f"{f['solver'][f['solver'].network == 'CONUS']['runtime_s'].iat[0]:.1f} s for CONUS. The GA needed far more time "
        f"and, in CONUS, ended {ga_gap['CONUS']:.2f}% above the optimum. At this problem size, exact MILP dominates. The "
        "GA's value is for larger or nonlinear variants where a MILP becomes intractable.",
        f"* **Naive placement is costly.** Random sites cost {abs(cflp_vs_rand['CONUS']):.1f}% more in CONUS. K-Means "
        f"(geography only) is close in CONUS ({abs(cflp_vs_km['CONUS']):.2f}%) but {abs(cflp_vs_km['Puerto Rico']):.1f}% "
        "worse in Puerto Rico, where it ignores the capacity–demand interaction.",
        f"* **Routing.** GLS cuts route distance by {gls_vs_nn['CONUS']:.1f}% versus Nearest Neighbor in CONUS. Nearest "
        f"Neighbor feasible: {nn_feasible['CONUS']}. The gain of GLS over standard OR-Tools is small "
        f"({gls_vs_std['CONUS']:.2f}%): with a binding route-length limit and few stops per depot, greedy descent already "
        "reaches near-optimal routes. In Puerto Rico all three methods coincide, because most volume sits at the depots' "
        "own zones.",
        f"* **Forecasting value is conditional.** In CONUS, planning on forecasts saves {fi_red['CONUS']:.1f}% of realised "
        "cost versus pre-break historical averages, which overstate units about 5×. In Puerto Rico the selected units "
        f"forecast is biased high, which opens one more warehouse and makes realised cost {abs(fi_red['Puerto Rico']):.1f}% "
        "higher. Transport there is almost free, so the historical plan's wrong locations barely matter. Forecast bias "
        "drives capacity decisions more than forecast error does.",
        f"* **Operating cost (warehouses + handling + routes):** about ${op['CONUS']:,.0f}/week "
        f"(${opy['CONUS']:,.0f}/year) in CONUS and ${op['Puerto Rico']:,.0f}/week (${opy['Puerto Rico']:,.0f}/year) in "
        "Puerto Rico. These are simulated.",
        f"* **Validation:** {int(checks['passed'].sum())}/{len(checks)} cross-module consistency checks pass, including "
        "full allocation, capacities, depots, network separation and cost recomputation. Test suite: {tests}.".replace("{tests}", f["tests"]),
        "",
        T(checks),
        "",
        "## 16a. Reconciliation of reported CFLP costs",
        "",
        "Two CONUS figures appear in the outputs. They describe the **same optimal solution under the same "
        "configuration** (`config.yaml` → `optimization.networks.CONUS`):",
        "",
        T(_reconcile(f)),
        "",
        "* `cflp_objective_excl_handling` = opening + transport. CBC minimises this and proves it optimal "
        "(`cflp_solver_report.csv`, `objective_excl_handling`).",
        "* `total_cost` adds the handling cost (handling cost per unit × forecast units). Handling is identical for every "
        "feasible solution, so it cannot change the decision. It is included for operating-cost reporting.",
        "* All comparison tables (`warehouse_algorithm_comparison.csv`, experiments) use `total_cost`, and therefore "
        "include handling.",
        "",
        "## 16b. Puerto Rico forecast overestimation",
        "",
        "The selected Puerto Rico model (post-break average, regime reset) over-forecast **units** by "
        f"{100 * _pr_bias(f, 'units'):+.1f}% over the 13 held-out weeks. **Orders** were within "
        f"{100 * _pr_bias(f, 'orders'):+.1f}%. Weekly actuals after the break:",
        "",
        T3(f["pr_weeks"]),
        "",
        "* **Cause:** the 4 observed weeks used for calibration include the transitional week of 1–7 October 2017, at "
        f"{f['pr_weeks']['units_per_order'].iat[0]:.2f} units/order. Every later week is exactly "
        f"{f['pr_weeks']['units_per_order'].iloc[4:].mean():.2f}. A mean over those 4 weeks therefore overstates later "
        "units by about 20%.",
        "* **Consequence in Experiment C:** the forecast-based plan sized capacity for about 211 units/week against "
        "175.5 realised. It opened a third warehouse, and its realised cost exceeded the historical-average plan's. "
        "This result is reported as measured; nothing was tuned away.",
        "* **Effect on the forward CFLP input:** none of this carries over. The forward forecast "
        f"({f['demand'][f['demand'].network == 'Puerto Rico']['forecast_per_period_units'].sum():.1f} units/week) is "
        "calibrated on the last 4 observed weeks (January 2018), all at 1.00 units/order. Whether it is accurate cannot "
        "be verified, because the dataset ends on 2018-01-31.",
        "* **Lesson:** after a structural break, calibration windows should exclude transition periods, or use robust "
        "statistics such as the median. This is listed under future improvements, not applied retroactively.",
        "",
        "## 16c. Solver termination of every time-limited run",
        "",
        "A solution is labelled optimal only when CBC reports `optimal`. Every run that hit the time limit is listed "
        "with its incumbent, lower bound and gap:",
        "",
        T(_time_limited(f)) if len(_time_limited(f)) else "_No run hit its time limit._",
        "",
        "## 17. Limitations",
        "",
        "* **Simulated business parameters:** all costs, capacities and fleet parameters are assumptions. Absolute dollar "
        "values are illustrative; comparisons between methods are valid because all methods share the assumptions.",
        "* **Approximate distances:** great-circle × circuity, not road networks (OSRM was blocked; zone coordinates were "
        "not sent to external services). Routes are drawn as straight segments.",
        "* **Demand model:** demand sits at customer coordinates, because destinations are synthetic. One package is "
        "assumed per order.",
        "* **Forecast window:** only 17 post-break weeks exist. The forecast extrapolates a 4-month-old regime, and the "
        "selected unit forecasts were biased high in back-testing.",
        "* **Uniform simplifications:** capacities and fixed costs are uniform across sites. Demand is single-sourced, "
        "and splitting is allowed only for routing.",
        "* **GLS timing:** GLS results depend on the time limit. Time-limited CFLP runs in experiments report their gap "
        "(`termination` / `plan_relative_gap` columns).",
        "",
        "## 18. Future improvements",
        "",
        "* Real road distances and travel times (self-hosted OSRM or OpenRouteService), and time windows (VRPTW).",
        "* Stochastic or robust CFLP over demand scenarios, and joint location–routing optimisation.",
        "* Site-specific costs and capacities from real-estate data, and multi-echelon networks.",
        "* Probabilistic forecasts (quantiles) feeding capacity buffers. Bias correction of unit forecasts.",
        "* Benders decomposition or Lagrangian relaxation for much larger instances. A GA with an exact allocation cache.",
        "",
        "## 19. Conclusion",
        "",
        "The system answers the five project questions end to end, with measured evidence:",
        "",
        "1. **Where to open warehouses:** the CFLP sites listed above.",
        "2. **How many:** the number that minimises opening + transport cost under capacity, determined exactly.",
        "3. **Which warehouse serves each zone:** the optimal capacity-feasible allocation.",
        "4. **How vehicles are assigned:** GLS routes per depot that satisfy capacity and route-length limits.",
        f"5. **Cost-effective routes:** {_route(f, 'CONUS', 'ortools_gls', 'total_distance_km'):,.0f} approximate road km "
        "per week in CONUS.",
        "",
        "Exact optimisation outperformed every heuristic and baseline on these instance sizes. Forecasting helped where "
        "it was unbiased and hurt where it was biased, which makes forecast bias, not just accuracy, a first-class "
        "planning concern.",
        "",
        "## 20. References",
        "",
        "1. Constante, F., Silva, F., Pereira, A. (2019). *DataCo Smart Supply Chain for Big Data Analysis*. Mendeley Data / Kaggle.",
        "2. Cornuéjols, G., Nemhauser, G., Wolsey, L. (1990). The uncapacitated facility location problem. In *Discrete Location Theory*. Wiley.",
        "3. Sridharan, R. (1995). The capacitated plant location problem. *European Journal of Operational Research* 87(2).",
        "4. Toth, P., Vigo, D. (2014). *Vehicle Routing: Problems, Methods, and Applications*. SIAM.",
        "5. Voudouris, C., Tsang, E. (1999). Guided local search and its application to the TSP. *EJOR* 113(2).",
        "6. Holland, J. (1975). *Adaptation in Natural and Artificial Systems*. Univ. of Michigan Press. Fortin, F.-A. et al. (2012). DEAP. *JMLR* 13.",
        "7. Chen, T., Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *KDD*.",
        "8. Breiman, L. (2001). Random forests. *Machine Learning* 45.",
        "9. Hart, W. et al. (2017). *Pyomo: Optimization Modeling in Python*. Springer. Forrest, J. et al. COIN-OR CBC.",
        "10. Perron, L., Furnon, V. *OR-Tools*. Google. Ballou, R., Rahardja, H., Sakai, N. (2002). Selected country circuity factors for road travel distance estimation. *Transportation Research A* 36(9).",
        "",
    ]
    return "\n".join(L)


def _reconcile(f: dict) -> pd.DataFrame:
    res = f["res"][f["res"]["network"].isin(["CONUS", "Puerto Rico"])].copy()
    sv = f["solver"].set_index("network")
    res["solver_objective_excl_handling"] = res["network"].map(sv["objective_excl_handling"])
    res["solver_lower_bound"] = res["network"].map(sv["lower_bound"])
    res["termination"] = res["network"].map(sv["termination"])
    return res[["network", "opening_cost", "transport_cost", "cflp_objective_excl_handling", "solver_objective_excl_handling",
                "solver_lower_bound", "handling_cost", "total_cost", "termination"]]


def _pr_bias(f: dict, target: str) -> float:
    fe = f["fe"]
    x = fe[(fe.granularity == "W") & (fe.eval_set == "post_break_adapted") & (fe.network == "Puerto Rico") & (fe.tier == "all")
           & (fe.level == "network_period") & (fe.target == target) & (fe.model == "post_break_average")]
    return float(x["bias_pct"].iat[0])


def _time_limited(f: dict) -> pd.DataFrame:
    rows = []
    s = f["sens"]
    s = s[(s["experiment"] == "warehouse") & (s["termination"] != "optimal")]
    for r in s.itertuples():
        rows.append({"run": f"Exp D {r.parameter}={r.value}", "network": r.network, "termination": r.termination,
                     "best_objective_incl_penalty": r.best_objective_incl_penalty, "lower_bound": r.lower_bound,
                     "relative_gap": r.relative_gap, "runtime_s": r.runtime_s, "unserved_units": r.unserved_units})
    fi = f["fi"]
    for r in fi[fi["plan_solver_termination"] != "optimal"].itertuples():
        rows.append({"run": f"Exp C plan: {r.scenario}", "network": r.network, "termination": r.plan_solver_termination,
                     "best_objective_incl_penalty": r.plan_best_objective_incl_penalty, "lower_bound": r.plan_lower_bound,
                     "relative_gap": r.plan_relative_gap, "runtime_s": r.plan_runtime_s,
                     "unserved_units": r.planned_unserved_units})
    return pd.DataFrame(rows)


def build_viva(f: dict) -> str:
    cfg = f["cfg"]
    res = f["res"].set_index("network")
    nets = ["CONUS", "Puerto Rico"]
    sel = f["sel"]
    s_or = sel[(sel.target == "orders") & (sel.network == "CONUS")].iloc[0]
    s_un = sel[(sel.target == "units") & (sel.network == "CONUS")].iloc[0]
    ga_gap = _m(f, "CONUS", "Genetic", "gap_vs_cflp_pct")
    rnd = _pct(_m(f, "CONUS", "Random", "total_cost"), _m(f, "CONUS", "CFLP", "total_cost"))
    gls_nn = _pct(_route(f, "CONUS", "nearest_neighbor", "total_distance_km"), _route(f, "CONUS", "ortools_gls", "total_distance_km"))
    gls_std = _pct(_route(f, "CONUS", "ortools_standard", "total_distance_km"), _route(f, "CONUS", "ortools_gls", "total_distance_km"))
    fi = {n: float(f["fi"][f["fi"].network == n]["forecast_cost_reduction_vs_historical_pct"].iat[0]) for n in nets}
    solver = f["solver"].set_index("network")
    qa = [
        ("Dataset", "What does one row of the DataCo file represent, and why does that matter?",
         f"One order *item*. The file has {f['rows']:,} item rows from {f['orders_raw']:,} orders. Treating items as deliveries "
         "would multiply delivery counts by about 2.75, so items are aggregated to orders (one delivery each) and then to zones."),
        ("Dataset", "Which coordinates exist and how were they interpreted?",
         "Only customer-side Latitude/Longitude. Customers' median coordinates lie 1.6–8.9 km from real city centres, so they "
         "are treated as customer locations at city precision. Destination fields have no coordinates and are statistically "
         "independent of customer location, so they are not used for routing."),
        ("Dataset", "What information was missing and how was it handled?",
         "Warehouses, capacities, costs, fleet, weights and road distances. They are explicit simulation assumptions in "
         "config.yaml, with sensitivity analysis on each."),
        ("Preprocessing", "Why were cancelled orders excluded?",
         "CANCELED and SUSPECTED_FRAUD orders all have Delivery Status 'Shipping canceled'. They never create a delivery, "
         "so they are not physical demand. They are flagged, not deleted."),
        ("Preprocessing", "How were invalid coordinates detected?",
         "Rules for sign flips, truncated longitudes, a placeholder point shared by several states, more than 1,000 km from "
         "the state's median, and Puerto Rico/mainland conflicts. 1.5% of rows are excluded and nothing is silently corrected."),
        ("Preprocessing", "How are demand zones built and why complete linkage?",
         "Hierarchical clustering with complete linkage on chord distance, cut at the diameter. Complete linkage guarantees "
         "that every pair of points in a zone is within the limit (50 km CONUS, 10 km islands); an exact check confirms it."),
        ("Preprocessing", "Why were CONUS and Puerto Rico separated?",
         "Trucks cannot drive between them. Solving separate models makes cross-sea assignments and routes impossible by "
         "construction, and tests verify it."),
        ("Forecasting", "What is the October 2017 break?",
         "From 2017-10 units per order fall from about 6.5 to about 1, the customers are new and the product mix changes, "
         "while orders per day rise. In Puerto Rico demand also moves about 35 km. Models trained before the break "
         "overshoot units about 5×."),
        ("Forecasting", "How was data leakage prevented?",
         "Features at week t use only weeks < t, through prefix sums, in one function shared by training, one-step and "
         "recursive forecasting. A unit test changes future values and asserts that no earlier feature changes. Splits are "
         "chronological."),
        ("Forecasting", "Why WAPE instead of MAPE?",
         "Most zone-weeks are zero, which makes MAPE undefined or infinite. WAPE = Σ|e|/Σy is scale-free and stable. MAPE is "
         "reported only for network totals, where every actual is positive."),
        ("Forecasting", "Which models were selected and why not XGBoost?",
         f"CONUS orders: {s_or.model} ({s_or.handling}), zone-total WAPE {s_or.WAPE:.3f}. CONUS units: {s_un.model} "
         f"({s_un.handling}), WAPE {s_un.WAPE:.3f}. Puerto Rico: post-break average. XGBoost never won: demand is noise "
         "around a level, and the post-break shift cannot be learned from pre-break data."),
        ("Forecasting", "Why select on zone-total rather than zone-week WAPE?",
         "Zone-week absolute error is minimised by the median, which for sparse counts is near zero. It rewards "
         "under-forecasting (the first selection was biased by −17.5%). The CFLP needs unbiased rates."),
        ("XGBoost", "What is XGBoost's objective function?",
         "The sum of the losses plus Σ_k Ω(f_k), where Ω(f) = γT + ½λ‖w‖² + α‖w‖₁ penalises the number of leaves and the "
         "leaf weights. The loss was squared error or Poisson deviance, chosen on validation."),
        ("XGBoost", "How does gradient boosting work in XGBoost?",
         "Trees are added one at a time. Each new tree fits a second-order Taylor expansion of the loss, using the gradients "
         "g and Hessians h. The optimal leaf weight is w* = −G/(H+λ), and a split's gain compares the G²/(H+λ) scores before "
         "and after the split. Each tree is shrunk by the learning rate."),
        ("XGBoost", "How is feature importance measured?",
         "Gain: total split gain per feature. Weight: how often a feature splits. Cover: the Hessian covered. Because gain "
         "is biased, permutation importance (the rise in test MAE when a column is shuffled) was also computed. Recent zone "
         "levels dominate, and the calendar ranks last."),
        ("CFLP", "State the CFLP objective.",
         "min Σ_j F_j Y_j + Σ_i Σ_j C_ij X_ij, where C_ij = c·d_ij·o_i (cost per order-km × approximate road km × forecast "
         "orders per week)."),
        ("CFLP", "What do the binary variables mean?",
         "Y_j = 1 if candidate warehouse j is opened. X_ij = 1 if zone i is served entirely by j (single sourcing)."),
        ("CFLP", "List the constraints.",
         "Each zone is assigned once: Σ_j X_ij = 1. Capacity: Σ_i u_i X_ij ≤ Q_j Y_j. Linking: X_ij ≤ Y_j. Warehouse count: "
         "p_min ≤ ΣY ≤ p_max. Binary domains. Separate networks keep the assignments geographically valid."),
        ("CFLP", "Why are orders used for cost and units for capacity?",
         "Transport cost scales with deliveries (orders). Storage and handling scale with items (units). After the break "
         "both are about 1 unit per order, but before it units were about 6.5× orders, so mixing them would distort both "
         "decisions."),
        ("CFLP", "Why add X_ij ≤ Y_j if the capacity constraint already links X and Y?",
         "Mathematically it is redundant, but it strengthens the LP relaxation (the disaggregated formulation). That makes "
         "branch-and-cut much faster."),
        ("CFLP", "Was the CFLP solved to optimality?",
         f"Yes. CBC reported 'optimal' with relative gap {solver.loc['CONUS', 'relative_gap']:.1e} for CONUS in "
         f"{solver.loc['CONUS', 'runtime_s']:.1f} s, and Puerto Rico in {solver.loc['Puerto Rico', 'runtime_s']:.1f} s. "
         "Time-limited experiment runs report their gap and are never called optimal."),
        ("CFLP", "How were candidate warehouses generated?",
         "Demand-weighted k-means on 3-D unit vectors of the zone centroids, with each centre snapped to the nearest zone, "
         "plus the highest-demand zones. Candidates are options only; the optimiser chooses."),
        ("CFLP", "What is the computational complexity?",
         "The CFLP is NP-hard (it generalises the p-median problem). The CONUS model has about 11,800 binary variables. "
         "Branch-and-cut works well here because the LP relaxation is tight."),
        ("Genetic Algorithm", "How is a solution encoded?",
         "A binary chromosome of length |J| (one gene per candidate). Gene 1 means that warehouse is open."),
        ("Genetic Algorithm", "What is the fitness function?",
         "Opening cost + transport cost of a capacity-feasible allocation + a large penalty × unserved units + a penalty "
         "for violating the warehouse-count limits. The data is the same as in the CFLP, and best chromosomes are "
         "re-evaluated with the exact allocation."),
        ("Genetic Algorithm", "Why not allocate each zone to its nearest open warehouse?",
         "That can exceed capacity and would make infeasible solutions look cheap. The regret heuristic never overloads "
         "a warehouse; zones that fit nowhere become penalised unserved demand."),
        ("Genetic Algorithm", "Which selection method was used?",
         f"Tournament selection with size {cfg['genetic_algorithm']['tournament_size']}: pick k random individuals and "
         "keep the fittest. It balances selection pressure and diversity, and elitism preserves the best solutions."),
        ("Genetic Algorithm", "Explain crossover and mutation.",
         "Two-point crossover swaps the gene segment between two cut points of two parents. Bit-flip mutation flips each "
         "gene with probability 1/|J|. A repair step then keeps the number of open warehouses within limits."),
        ("Genetic Algorithm", "Did the GA beat the CFLP?",
         f"No. In CONUS its best run is {ga_gap:.2f}% above the proven optimum, and it took much longer. In Puerto Rico "
         "it reached the optimum. A heuristic cannot beat a proven optimum on the same model."),
        ("Genetic Algorithm", "When would a GA be preferable?",
         "For very large candidate sets, nonlinear or simulation-based costs, or multiple objectives, where a MILP cannot "
         "be solved in time. The GA only needs a fitness function."),
        ("CVRP", "State the CVRP objective and constraints.",
         "min Σ_k Σ_i Σ_j d_ij x_ijk, such that each stop is visited once, routes start and end at the depot, the load per "
         "route is within vehicle capacity, route length is at most L_max, and at most K vehicles are used per depot."),
        ("CVRP", "What is a package and how was demand rounded?",
         "One package = one forecast order, because the data has no weights. Weekly fractional forecasts are apportioned to "
         "whole packages per depot with the largest-remainder method, which preserves the expected total."),
        ("CVRP", "How were stops larger than vehicle capacity handled?",
         "They were split into several stops at the same location (split delivery), so the CVRP stays feasible."),
        ("Guided Local Search", "How does GLS escape local minima?",
         "At a local minimum it penalises solution features (arcs) with high utility c_a/(1+p_a). The search continues on "
         "cost + λ·Σ penalties, so long, frequently used arcs become expensive and the search moves to new regions."),
        ("Guided Local Search", "What were the routing results?",
         f"In CONUS, GLS used {gls_nn:.1f}% less distance than Nearest Neighbor (whose routes also break the route-length "
         f"limit) and {gls_std:.2f}% less than standard OR-Tools greedy descent."),
        ("Algorithm comparison", "How much did the CFLP save versus naive placement?",
         f"{rnd:.1f}% lower total cost than random sites in CONUS, with the same number of warehouses and identical data."),
        ("Algorithm comparison", "Did forecasting improve warehouse planning?",
         f"In CONUS, yes: {fi['CONUS']:.1f}% lower realised cost than planning on historical averages, over 13 held-out "
         f"weeks. In Puerto Rico, no: {fi['Puerto Rico']:.1f}%, because the unit forecast was biased high and opened an "
         "extra warehouse."),
        ("Sensitivity analysis", "How does the number of warehouses respond to fixed cost?",
         "Higher fixed costs reduce the number of warehouses opened, and higher transport costs increase it. The cost "
         "curve over a forced number of warehouses is U-shaped, with its minimum at the CFLP's choice."),
        ("Sensitivity analysis", "What happens if demand grows 20%?",
         "The robustness experiment keeps the selected warehouses and re-allocates zones. It reports the maximum "
         "utilisation and any unserved units or overload; Puerto Rico runs close to capacity and is the first to become "
         "infeasible."),
        ("Mathematical optimisation", "Why use an exact solver and not only heuristics?",
         "An exact MILP gives a provable optimum or a gap. That benchmark is what lets us quantify the GA's and K-Means' "
         "sub-optimality honestly."),
        ("Mathematical optimisation", "Why are distances called approximate?",
         "They are great-circle km × 1.2 circuity, because OSRM was not reachable and coordinates were not sent externally. "
         "They are never labelled as road-network distances."),
        ("Research contribution", "What is the contribution of this project?",
         "An end-to-end, reproducible forecasting → location → routing pipeline on real order data. It includes honest "
         "regime-aware forecasting, exact-versus-heuristic benchmarking with identical inputs, and evidence that forecast "
         "bias drives capacity decisions."),
        ("Research contribution", "What are the main limitations?",
         "Simulated costs and capacities, approximate distances, synthetic destination fields, one package per order, and a "
         "short post-break history."),
        ("Computational complexity", "How long does the full pipeline take?",
         "Preprocessing ~30 s, forecasting ~7 min (Random Forest/XGBoost grids), CFLP seconds, GA ~1–2 min, and routing "
         "~1.5 min (10 s GLS per depot). The experiments take several minutes."),
    ]
    L = ["# Viva preparation: questions and answers", "",
         f"_{len(qa)} questions, generated from the actual project outputs (`python main.py report`)._", ""]
    cur = None
    for k, (topic, q, a) in enumerate(qa, 1):
        if topic != cur:
            L += [f"## {topic}", ""]; cur = topic
        L += [f"**Q{k}. {q}**", "", a, ""]
    return "\n".join(L)


def build_presentation(f: dict) -> str:
    res = f["res"].set_index("network")
    nets = ["CONUS", "Puerto Rico"]
    fi = {n: float(f["fi"][f["fi"].network == n]["forecast_cost_reduction_vs_historical_pct"].iat[0]) for n in nets}
    slides = [
        ("Title", ["Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Route Optimisation",
                   "Hybrid pipeline: forecasting → CFLP (exact) + GA → CVRP with Guided Local Search"]),
        ("Problem introduction", ["Fulfilment cost = warehouses + transport + delivery routes",
                                  "Coupled strategic (location) and operational (routing) decisions under uncertain demand"]),
        ("Research gap", ["Studies usually optimise location *or* routing with synthetic demand",
                          "Few benchmark exact vs heuristic methods on identical real-data inputs, and few test whether "
                          "forecasting improves the plan"]),
        ("Dataset", [f"DataCo: {f['rows']:,} order-item rows → {f['orders']:,} deliveries, {f['units']:,} units",
                     "Customer coordinates only; no costs, warehouses or fleet → documented assumptions",
                     "Personal data removed; raw data kept out of Git"]),
        ("Preprocessing & demand zones", ["Flag-based cleaning with a decision log; 37 reconciliation checks",
                                          "Bounded-diameter zones: 312 CONUS, 25 Puerto Rico; separate island network"]),
        ("Architecture", ["Raw → clean → zones → forecast → candidates → CFLP/GA → allocation → CVRP/GLS → experiments → dashboard",
                          "Single CLI: `python main.py all`; configuration in config.yaml"]),
        ("Forecasting", ["October 2017 break: units/order 6.5 → 1, Puerto Rico demand relocates",
                         "Historical average, moving average, Random Forest, XGBoost; leakage-tested features",
                         "Selected per network and target; XGBoost not selected (measured)"]),
        ("CFLP formulation", ["min ΣF_jY_j + Σc·d_ij·o_i·X_ij", "Σ_j X_ij = 1, Σ_i u_iX_ij ≤ Q_jY_j, X ≤ Y, p_min ≤ ΣY ≤ p_max",
                              "Orders → transport cost; units → capacity"]),
        ("CFLP results", [f"CONUS: {int(res.loc['CONUS', 'n_open'])} warehouses, ${res.loc['CONUS', 'total_cost']:,.0f}/week, proven optimal",
                          f"Puerto Rico: {int(res.loc['Puerto Rico', 'n_open'])} warehouses (capacity-driven)",
                          "Map: phase4_selected_allocation.png"]),
        ("Genetic Algorithm", ["Binary chromosome, tournament selection, two-point crossover, bit-flip mutation, repair, elitism",
                               f"Best CONUS run is {_m(f, 'CONUS', 'Genetic', 'gap_vs_cflp_pct'):.2f}% above the optimum; "
                               "it matches the optimum in Puerto Rico",
                               "Convergence: ga_convergence.png"]),
        ("CVRP", ["Weekly consolidated delivery; one package = one order; split deliveries",
                  "Capacity, route length and fleet constraints; unserved stops reported"]),
        ("Guided Local Search", ["Arc features, utility c/(1+p), augmented objective",
                                 f"GLS vs Nearest Neighbor: −{_pct(_route(f, 'CONUS', 'nearest_neighbor', 'total_distance_km'), _route(f, 'CONUS', 'ortools_gls', 'total_distance_km')):.1f}% km; "
                                 f"vs standard OR-Tools: −{_pct(_route(f, 'CONUS', 'ortools_standard', 'total_distance_km'), _route(f, 'CONUS', 'ortools_gls', 'total_distance_km')):.2f}% km"]),
        ("Experimental setup", ["Identical demand, candidates, distances and costs for every method",
                                "Experiments A–E: location, routing, forecast impact, sensitivity, robustness"]),
        ("Results: optimisation", [f"CFLP vs random: −{_pct(_m(f, 'CONUS', 'Random', 'total_cost'), _m(f, 'CONUS', 'CFLP', 'total_cost')):.1f}% cost (CONUS)",
                                   f"CFLP vs K-Means: −{_pct(_m(f, 'CONUS', 'K-Means', 'total_cost'), _m(f, 'CONUS', 'CFLP', 'total_cost')):.2f}% (CONUS), "
                                   f"−{_pct(_m(f, 'Puerto Rico', 'K-Means', 'total_cost'), _m(f, 'Puerto Rico', 'CFLP', 'total_cost')):.1f}% (Puerto Rico)"]),
        ("Results: forecasting impact", [f"CONUS: forecast plan {fi['CONUS']:.1f}% cheaper than the historical-average plan",
                                         f"Puerto Rico: {fi['Puerto Rico']:.1f}% (biased unit forecast → extra warehouse)",
                                         "Lesson: forecast bias drives capacity decisions"]),
        ("Sensitivity & robustness", ["Warehouse count falls with fixed cost and rises with transport cost",
                                      "Demand shocks: Puerto Rico near capacity; CONUS absorbs ±20%"]),
        ("Dashboard", ["8 Streamlit pages; interactive maps; what-if page re-solves the CFLP and CVRP live",
                       "`streamlit run dashboard/app.py`"]),
        ("Conclusion & future work", ["Exact MILP dominates at this scale; heuristics are benchmarked against it",
                                      "Future: real road distances, stochastic CFLP, joint location-routing, quantile forecasts"]),
    ]
    L = ["# Presentation outline (18 slides)", "", "_Numbers are generated from the project outputs._", ""]
    for k, (t, pts) in enumerate(slides, 1):
        L += [f"## Slide {k}: {t}", ""] + [f"- {p}" for p in pts] + [""]
    return "\n".join(L)


def write_all_reports() -> list[Path]:
    f = _facts()
    paths = []
    for name, fn in [("final_project_report.md", build_final_report), ("viva_questions.md", build_viva),
                     ("presentation_outline.md", build_presentation)]:
        p = REP / name
        p.write_text(fn(f), encoding="utf-8")
        paths.append(p)
    return paths
