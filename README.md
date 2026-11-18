# Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimization

An end-to-end, research-oriented optimisation system built on the **DataCo Smart Supply Chain** dataset:

data cleaning → demand zones → **demand forecasting** (historical average, moving average, Random Forest, XGBoost) →
**Capacitated Facility Location Problem** (Pyomo + CBC, exact) → **Genetic Algorithm** (DEAP) comparison →
customer allocation → **Capacitated Vehicle Routing** (OR-Tools, Guided Local Search) → experiments → Streamlit dashboard.

## Problem statement and objectives

Given historical orders, the system decides:

1. **Where** to open warehouses and **how many**.
2. **Which warehouse** serves each demand zone, within capacity.
3. **How vehicles** are assigned and routed from each warehouse.

It minimises warehouse opening, transport and route costs subject to warehouse and vehicle capacity, and reports any
unserved demand explicitly. Every optimisation method is compared with baselines on identical inputs, and the value of
forecasting is measured on held-out demand.

## Dataset

* **Source:** [Kaggle: DataCo Smart Supply Chain for Big Data Analysis](https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis)
* **Size:** 180,519 order-item rows × 53 columns, from 65,752 orders, January 2015 to January 2018.

**Limitations of the data, and how they are handled:**

* **Coordinates:** only customer-side `Latitude`/`Longitude` exist (US and Puerto Rico).
  * Destination fields (`Order City`/`Order Country`) have no coordinates and are statistically independent of customer
    location. Demand is therefore located at customer coordinates, and international destinations are never routed.
* **Missing business data:** there are no warehouses, capacities, costs, fleet, weights or road distances.
  * These are **documented simulation assumptions** in `config.yaml`.
* **October 2017 distribution break:** units per order fall from about 6.5 to about 1, and Puerto Rico demand relocates
  about 35 km.
* **Personal data:** customer names and streets are present in the raw file.
  * They are dropped before any output is written, the raw data is git-ignored, and a test enforces this.

## Architecture

```
python main.py preprocess   Phase 2  cleaning, demand zones, EDA            -> data/processed, data/outputs/eda_*
python main.py forecast     Phase 3  4 forecasting approaches, selection    -> cflp_zone_demand_forecast.csv
python main.py warehouse    Phase 4  CFLP per network (Pyomo + CBC)         -> optimal_warehouse_locations.csv ...
python main.py genetic      Phase 5  GA vs CFLP vs K-Means vs random        -> warehouse_algorithm_comparison.csv
python main.py routing      Phase 6  CVRP: Nearest Neighbor / OR-Tools / GLS -> optimized_delivery_routes.csv ...
python main.py evaluate     Phase 8  experiments A-E, consistency checks, figures
python main.py report       Phase 10 final report, viva questions, presentation outline
python main.py all          everything (reuses valid Phase 2/3 outputs unless --force)
streamlit run dashboard/app.py   Phase 9 dashboard
```

| Module | Responsibility |
|---|---|
| `src/data_loader.py`, `src/data_inspection.py` | Kaggle download, loading, Phase 1 quality inspection |
| `src/preprocessing.py`, `src/demand_analytics.py` | Cleaning, demand zones, aggregation, EDA |
| `src/forecasting.py` | Leakage-free features, 4 approaches, evaluation, CFLP hand-off |
| `src/distance_calculator.py` | Haversine and approximate road distance (× circuity factor) |
| `src/warehouse_cflp.py` | Candidate generation, CFLP model, independent cost evaluation |
| `src/customer_allocation.py` | Capacity-feasible regret allocation, allocation and capacity tables |
| `src/genetic_algorithm.py` | DEAP GA, K-Means and random baselines |
| `src/vehicle_routing.py` | CVRP instances, Nearest Neighbor, OR-Tools standard and GLS, feasibility checks |
| `src/pipeline.py` | Orchestration, output validation, run-config logging |
| `src/experiments.py`, `src/evaluation.py` | Experiments A-E, metrics, consistency checks, final summary |
| `src/visualization.py`, `src/optimization_visualization.py` | Static figures and folium maps |
| `src/reports.py`, `src/final_reports.py` | Generated reports |
| `dashboard/app.py` | Streamlit application (8 pages) |

**Technology:** Python 3.11+ (tested on 3.13), pandas, NumPy, scikit-learn, XGBoost, Pyomo, CBC (HiGHS fallback),
DEAP, OR-Tools, folium, Plotly, Matplotlib, Streamlit, pytest.

## Installation

```bash
pip install -r requirements.txt
```

```bash
sudo apt-get install coinor-cbc
```

Then get the dataset, either through the Kaggle API (see `data/raw/README.md`) or from a manually downloaded zip:

```bash
python main.py download
```

```bash
python main.py download --zip archive.zip
```

## Configuration

`config.yaml` holds every parameter:

* the dataset and cleaning rules;
* the zone diameters;
* forecasting splits and grids;
* per-network CFLP assumptions (`optimization.networks`: capacity in units/week, fixed cost/week, cost per order-km,
  minimum and maximum warehouses);
* GA settings and seeds;
* routing settings (vehicle capacity in packages, fleet, speed, maximum route km, GLS time limit);
* experiment grids.

The configuration used by each stage is saved in `data/outputs/run_configs/`.

## Execution

```bash
python main.py all
```

```bash
pytest -q
```

```bash
streamlit run dashboard/app.py
```

`python main.py all` reuses existing Phase 2/3 outputs; add `--force` to recompute them as well. Use `--quick` to skip
experiments C–E. The dashboard opens at http://localhost:8501.

**Dashboard pages:**

1. Executive overview
2. Data analytics
3. Demand forecasting
4. Warehouse optimisation
5. Delivery routing
6. Algorithm performance
7. What-if simulation (re-solves the CFLP and CVRP live)
8. Reports & downloads

## Methodology (summary)

* **CFLP:** $\min \sum_j F_jY_j + \sum_{ij} c\,d_{ij}\,o_i\,X_{ij}$, subject to:
  * each zone is assigned once: $\sum_j X_{ij}=1$;
  * capacity: $\sum_i u_iX_{ij}\le Q_jY_j$;
  * linking: $X_{ij}\le Y_j$;
  * warehouse count: $p_{min}\le\sum Y\le p_{max}$.

  Orders $o_i$ drive transport cost (deliveries); units $u_i$ consume capacity. CONUS and Puerto Rico are solved as
  separate models.
* **Genetic Algorithm:**
  * binary chromosome (one gene per candidate site);
  * fitness = opening + transport of a capacity-feasible allocation + penalties;
  * tournament selection, two-point crossover, bit-flip mutation, repair, elitism;
  * 5 seeds;
  * the best chromosome of each run is re-allocated exactly with CBC.
* **CVRP:** a weekly consolidated delivery plan with one package per order.
  * Constraints: vehicle capacity, maximum route length and fleet size; unserved stops are reported.
  * Methods compared:
    * Nearest Neighbor;
    * OR-Tools PATH_CHEAPEST_ARC + greedy descent;
    * OR-Tools Guided Local Search.
* **Distances:** great-circle × 1.2 circuity. These are **approximate road km**: OSRM was not reachable and coordinates
  were not sent to external services.

## Key results (weekly, simulated cost assumptions)

| Network | Method | Warehouses | Total cost USD/wk | Gap vs CFLP |
|---|---|---|---|---|
| CONUS | **CFLP (proven optimal, 0.9 s)** | 6 | **18,497** | 0 |
| CONUS | Genetic Algorithm (best of 5 seeds, 71 s) | 6 | 18,605 | +0.58% |
| CONUS | K-Means | 6 | 18,655 | +0.85% |
| CONUS | Random (mean of 30) | 6 | 30,118 | +62.8% |
| Puerto Rico | **CFLP** | 2 | **2,510** | 0 |
| Puerto Rico | Genetic Algorithm | 2 | 2,510 | 0 |
| Puerto Rico | K-Means | 2 | 3,206 | +27.8% |

Selected CONUS warehouses, with capacity utilisation:

| Warehouse | Location | Utilisation |
|---|---|---|
| WH-US-01 | Brooklyn, NY | 91% |
| WH-US-03 | Chicago, IL | 69% |
| WH-US-05 | Long Beach, CA | 86% |
| WH-US-14 | Dallas, TX | 51% |
| WH-US-31 | Livermore, CA | 44% |
| WH-US-37 | Hialeah, FL | 31% |

Puerto Rico uses two warehouses near Caguas (94% and 81%).

**Routing (CONUS, per week):**

| Method | Vehicles | Distance | Constraints |
|---|---|---|---|
| Guided Local Search | 16 | 31,610 km | all satisfied |
| Standard OR-Tools | 16 | 31,647 km | all satisfied |
| Nearest Neighbor | 13 | 38,636 km | 5 routes break the route-length limit |

GLS is 18.2% shorter than Nearest Neighbor and only 0.12% shorter than standard OR-Tools. In Puerto Rico all three
methods produce identical routes (7 vehicles, 174 km).

**Forecasting impact** (plans evaluated on 13 held-out weeks):

* **CONUS:** the forecast-based plan costs **29.5% less** than the historical-average plan, and is only 0.4% above the
  perfect-information optimum.
* **Puerto Rico:** the forecast-based plan costs **21.6% more**. Its unit forecast was biased high, which opened a third
  warehouse.

Sensitivity and robustness results: `reports/final_project_report.md` §15.

## Output files (`data/outputs/`)

| File | Content |
|---|---|
| `cflp_zone_demand_forecast.csv` | Zone demand forecast (CFLP input) |
| `optimal_warehouse_locations.csv`, `warehouse_capacity_report.csv` | Opened warehouses; all candidates with utilisation |
| `customer_warehouse_allocation.csv`, `selected_allocation.csv` | Zone → warehouse allocation |
| `warehouse_optimization_results.csv`, `cflp_solver_report.csv` | Cost summary; solver status, bound, gap, runtime |
| `genetic_algorithm_results.csv`, `ga_convergence.csv`, `warehouse_algorithm_comparison.csv` | GA runs and comparison |
| `optimized_delivery_routes.csv`, `vehicle_assignments.csv` | GLS stops and routes |
| `route_comparison.csv`, `route_distance_report.csv`, `route_feasibility_report.csv` | Routing comparison and checks |
| `experiment_*.csv`, `forecast_impact_comparison.csv`, `sensitivity_analysis.csv`, `robustness_analysis.csv` | Experiments A–E |
| `final_performance_summary.csv`, `consistency_checks.csv` | Headline KPIs (with actual/forecast/simulated provenance); cross-module checks |

**Reports** (`reports/`):

* `final_project_report.md`
* `viva_questions.md`
* `presentation_outline.md`
* phase reports `phase1`–`phase3`
* `figures/`, including interactive maps:
  * `phase4_warehouse_allocation_map.html`
  * `phase6_delivery_routes_map.html`

## Limitations

* **Simulated business parameters:** costs, capacities and fleet are assumptions. Method comparisons are valid
  because all methods share them; absolute dollar values are illustrative.
* **Approximate distances:** great-circle × circuity; routes are drawn as straight segments.
* **Demand model:** synthetic destination fields, and one package per order.
* **Short post-break history:** only 17 weeks after the October 2017 break.
* **Time-limited runs:** GLS results depend on its time limit. Time-limited CFLP runs in the experiments report their
  gap and are not called optimal.
