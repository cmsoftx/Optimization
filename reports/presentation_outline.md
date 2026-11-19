# Presentation outline (18 slides)

_Numbers are generated from the project outputs._

## Slide 1: Title

- Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Route Optimisation
- Hybrid pipeline: forecasting → CFLP (exact) + GA → CVRP with Guided Local Search

## Slide 2: Problem introduction

- Fulfilment cost = warehouses + transport + delivery routes
- Coupled strategic (location) and operational (routing) decisions under uncertain demand

## Slide 3: Research gap

- Studies usually optimise location *or* routing with synthetic demand
- Few benchmark exact vs heuristic methods on identical real-data inputs, and few test whether forecasting improves the plan

## Slide 4: Dataset

- DataCo: 180,519 order-item rows → 62,011 deliveries, 361,965 units
- Customer coordinates only; no costs, warehouses or fleet → documented assumptions
- Personal data removed; raw data kept out of Git

## Slide 5: Preprocessing & demand zones

- Flag-based cleaning with a decision log; 37 reconciliation checks
- Bounded-diameter zones: 312 CONUS, 25 Puerto Rico; separate island network

## Slide 6: Architecture

- Raw → clean → zones → forecast → candidates → CFLP/GA → allocation → CVRP/GLS → experiments → dashboard
- Single CLI: `python main.py all`; configuration in config.yaml

## Slide 7: Forecasting

- October 2017 break: units/order 6.5 → 1, Puerto Rico demand relocates
- Historical average, moving average, Random Forest, XGBoost; leakage-tested features
- Selected per network and target; XGBoost not selected (measured)

## Slide 8: CFLP formulation

- min ΣF_jY_j + Σc·d_ij·o_i·X_ij
- Σ_j X_ij = 1, Σ_i u_iX_ij ≤ Q_jY_j, X ≤ Y, p_min ≤ ΣY ≤ p_max
- Orders → transport cost; units → capacity

## Slide 9: CFLP results

- CONUS: 6 warehouses, $18,497/week, proven optimal
- Puerto Rico: 2 warehouses (capacity-driven)
- Map: phase4_selected_allocation.png

## Slide 10: Genetic Algorithm

- Binary chromosome, tournament selection, two-point crossover, bit-flip mutation, repair, elitism
- Best CONUS run is 0.58% above the optimum; it matches the optimum in Puerto Rico
- Convergence: ga_convergence.png

## Slide 11: CVRP

- Weekly consolidated delivery; one package = one order; split deliveries
- Capacity, route length and fleet constraints; unserved stops reported

## Slide 12: Guided Local Search

- Arc features, utility c/(1+p), augmented objective
- GLS vs Nearest Neighbor: −18.2% km; vs standard OR-Tools: −0.12% km

## Slide 13: Experimental setup

- Identical demand, candidates, distances and costs for every method
- Experiments A–E: location, routing, forecast impact, sensitivity, robustness

## Slide 14: Results: optimisation

- CFLP vs random: −38.6% cost (CONUS)
- CFLP vs K-Means: −0.85% (CONUS), −21.7% (Puerto Rico)

## Slide 15: Results: forecasting impact

- CONUS: forecast plan 29.5% cheaper than the historical-average plan
- Puerto Rico: -21.6% (biased unit forecast → extra warehouse)
- Lesson: forecast bias drives capacity decisions

## Slide 16: Sensitivity & robustness

- Warehouse count falls with fixed cost and rises with transport cost
- Demand shocks: Puerto Rico near capacity; CONUS absorbs ±20%

## Slide 17: Dashboard

- 8 Streamlit pages; interactive maps; what-if page re-solves the CFLP and CVRP live
- `streamlit run dashboard/app.py`

## Slide 18: Conclusion & future work

- Exact MILP dominates at this scale; heuristics are benchmarked against it
- Future: real road distances, stochastic CFLP, joint location-routing, quantile forecasts
