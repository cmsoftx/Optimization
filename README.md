# Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimization

An end-to-end, research-oriented pipeline built on the **DataCo Smart Supply Chain** dataset:
EDA → XGBoost demand forecasting → Capacitated Facility Location (Pyomo + CBC) →
Genetic Algorithm comparison (DEAP) → customer allocation → CVRP with Guided Local
Search (OR-Tools) → experiments → Streamlit dashboard.

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Dataset inspection: structure, quality, limitations | ✅ done (`reports/phase1_dataset_inspection.md`) |
| 2 | Preprocessing and EDA | ⏳ next |
| 3 | Demand forecasting (XGBoost) | — |
| 4 | CFLP (Pyomo + CBC) | — |
| 5 | Genetic algorithm vs CFLP | — |
| 6 | CVRP + Guided Local Search | — |
| 7 | Integrated pipeline | — |
| 8 | Experiments and sensitivity analysis | — |
| 9 | Streamlit dashboard | — |
| 10 | Final documentation | — |

## Quick start

```bash
pip install -r requirements.txt
sudo apt-get install coinor-cbc          # MILP solver used by the CFLP (HiGHS is the pip fallback)
python main.py download                  # Kaggle API (see data/raw/README.md), or:
python main.py download --zip archive.zip
python main.py inspect                   # Phase 1 report + CSVs
pytest -q
```

## Key findings from Phase 1 (from the actual file)

* 180,519 **order-item** rows = 65,752 orders (deliveries) from 20,652 customers, Jan 2015 – Jan 2018.
* The only coordinates are customer-side `Latitude`/`Longitude` (US + Puerto Rico). Destination
  fields (`Order City`/`Order Country`, 164 countries) have no coordinates and are not geographically
  coherent with the customers. The network is therefore designed on customer coordinates, with the
  **contiguous US** as the main network and Puerto Rico as a separate island sub-network.
* 2,727 rows (222 customers) have invalid or suspicious coordinates: sign flips, truncated longitudes,
  a placeholder point near the US centroid, and state mismatches. They are flagged, not silently fixed.
* From **2017-10** the generating process changes: units/month fall about 80% and items per order go from 3 to 1.
  Forecasting must handle this regime change.
* The dataset contains no warehouses, capacities, costs, fleet or road distances. These are introduced as
  labelled simulation assumptions in `config.yaml`.

## Layout

```
data/{raw,processed,outputs}   raw is git-ignored (licensed, contains PII)
notebooks/                     01_data_exploration.ipynb …
src/                           config, data_loader, data_inspection, distance_calculator, …
reports/                       generated Markdown reports + figures
tests/                         pytest suite
dashboard/                     Streamlit app (Phase 9)
main.py, config.yaml
```

The repository root is the `ecommerce_optimization/` project folder from the specification.
