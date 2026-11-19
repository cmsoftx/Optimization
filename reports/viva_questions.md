# Viva preparation: questions and answers

_44 questions, generated from the actual project outputs (`python main.py report`)._

## Dataset

**Q1. What does one row of the DataCo file represent, and why does that matter?**

One order *item*. The file has 180,519 item rows from 65,752 orders. Treating items as deliveries would multiply delivery counts by about 2.75, so items are aggregated to orders (one delivery each) and then to zones.

**Q2. Which coordinates exist and how were they interpreted?**

Only customer-side Latitude/Longitude. Customers' median coordinates lie 1.6–8.9 km from real city centres, so they are treated as customer locations at city precision. Destination fields have no coordinates and are statistically independent of customer location, so they are not used for routing.

**Q3. What information was missing and how was it handled?**

Warehouses, capacities, costs, fleet, weights and road distances. They are explicit simulation assumptions in config.yaml, with sensitivity analysis on each.

## Preprocessing

**Q4. Why were cancelled orders excluded?**

CANCELED and SUSPECTED_FRAUD orders all have Delivery Status 'Shipping canceled'. They never create a delivery, so they are not physical demand. They are flagged, not deleted.

**Q5. How were invalid coordinates detected?**

Rules for sign flips, truncated longitudes, a placeholder point shared by several states, more than 1,000 km from the state's median, and Puerto Rico/mainland conflicts. 1.5% of rows are excluded and nothing is silently corrected.

**Q6. How are demand zones built and why complete linkage?**

Hierarchical clustering with complete linkage on chord distance, cut at the diameter. Complete linkage guarantees that every pair of points in a zone is within the limit (50 km CONUS, 10 km islands); an exact check confirms it.

**Q7. Why were CONUS and Puerto Rico separated?**

Trucks cannot drive between them. Solving separate models makes cross-sea assignments and routes impossible by construction, and tests verify it.

## Forecasting

**Q8. What is the October 2017 break?**

From 2017-10 units per order fall from about 6.5 to about 1, the customers are new and the product mix changes, while orders per day rise. In Puerto Rico demand also moves about 35 km. Models trained before the break overshoot units about 5×.

**Q9. How was data leakage prevented?**

Features at week t use only weeks < t, through prefix sums, in one function shared by training, one-step and recursive forecasting. A unit test changes future values and asserts that no earlier feature changes. Splits are chronological.

**Q10. Why WAPE instead of MAPE?**

Most zone-weeks are zero, which makes MAPE undefined or infinite. WAPE = Σ|e|/Σy is scale-free and stable. MAPE is reported only for network totals, where every actual is positive.

**Q11. Which models were selected and why not XGBoost?**

CONUS orders: share_x_recent_level (regime_reset), zone-total WAPE 0.242. CONUS units: random_forest (recalibrated), WAPE 0.304. Puerto Rico: post-break average. XGBoost never won: demand is noise around a level, and the post-break shift cannot be learned from pre-break data.

**Q12. Why select on zone-total rather than zone-week WAPE?**

Zone-week absolute error is minimised by the median, which for sparse counts is near zero. It rewards under-forecasting (the first selection was biased by −17.5%). The CFLP needs unbiased rates.

## XGBoost

**Q13. What is XGBoost's objective function?**

The sum of the losses plus Σ_k Ω(f_k), where Ω(f) = γT + ½λ‖w‖² + α‖w‖₁ penalises the number of leaves and the leaf weights. The loss was squared error or Poisson deviance, chosen on validation.

**Q14. How does gradient boosting work in XGBoost?**

Trees are added one at a time. Each new tree fits a second-order Taylor expansion of the loss, using the gradients g and Hessians h. The optimal leaf weight is w* = −G/(H+λ), and a split's gain compares the G²/(H+λ) scores before and after the split. Each tree is shrunk by the learning rate.

**Q15. How is feature importance measured?**

Gain: total split gain per feature. Weight: how often a feature splits. Cover: the Hessian covered. Because gain is biased, permutation importance (the rise in test MAE when a column is shuffled) was also computed. Recent zone levels dominate, and the calendar ranks last.

## CFLP

**Q16. State the CFLP objective.**

min Σ_j F_j Y_j + Σ_i Σ_j C_ij X_ij, where C_ij = c·d_ij·o_i (cost per order-km × approximate road km × forecast orders per week).

**Q17. What do the binary variables mean?**

Y_j = 1 if candidate warehouse j is opened. X_ij = 1 if zone i is served entirely by j (single sourcing).

**Q18. List the constraints.**

Each zone is assigned once: Σ_j X_ij = 1. Capacity: Σ_i u_i X_ij ≤ Q_j Y_j. Linking: X_ij ≤ Y_j. Warehouse count: p_min ≤ ΣY ≤ p_max. Binary domains. Separate networks keep the assignments geographically valid.

**Q19. Why are orders used for cost and units for capacity?**

Transport cost scales with deliveries (orders). Storage and handling scale with items (units). After the break both are about 1 unit per order, but before it units were about 6.5× orders, so mixing them would distort both decisions.

**Q20. Why add X_ij ≤ Y_j if the capacity constraint already links X and Y?**

Mathematically it is redundant, but it strengthens the LP relaxation (the disaggregated formulation). That makes branch-and-cut much faster.

**Q21. Was the CFLP solved to optimality?**

Yes. CBC reported 'optimal' with relative gap 0.0e+00 for CONUS in 1.0 s, and Puerto Rico in 0.1 s. Time-limited experiment runs report their gap and are never called optimal.

**Q22. How were candidate warehouses generated?**

Demand-weighted k-means on 3-D unit vectors of the zone centroids, with each centre snapped to the nearest zone, plus the highest-demand zones. Candidates are options only; the optimiser chooses.

**Q23. What is the computational complexity?**

The CFLP is NP-hard (it generalises the p-median problem). The CONUS model has about 11,800 binary variables. Branch-and-cut works well here because the LP relaxation is tight.

## Genetic Algorithm

**Q24. How is a solution encoded?**

A binary chromosome of length |J| (one gene per candidate). Gene 1 means that warehouse is open.

**Q25. What is the fitness function?**

Opening cost + transport cost of a capacity-feasible allocation + a large penalty × unserved units + a penalty for violating the warehouse-count limits. The data is the same as in the CFLP, and best chromosomes are re-evaluated with the exact allocation.

**Q26. Why not allocate each zone to its nearest open warehouse?**

That can exceed capacity and would make infeasible solutions look cheap. The regret heuristic never overloads a warehouse; zones that fit nowhere become penalised unserved demand.

**Q27. Which selection method was used?**

Tournament selection with size 3: pick k random individuals and keep the fittest. It balances selection pressure and diversity, and elitism preserves the best solutions.

**Q28. Explain crossover and mutation.**

Two-point crossover swaps the gene segment between two cut points of two parents. Bit-flip mutation flips each gene with probability 1/|J|. A repair step then keeps the number of open warehouses within limits.

**Q29. Did the GA beat the CFLP?**

No. In CONUS its best run is 0.58% above the proven optimum, and it took much longer. In Puerto Rico it reached the optimum. A heuristic cannot beat a proven optimum on the same model.

**Q30. When would a GA be preferable?**

For very large candidate sets, nonlinear or simulation-based costs, or multiple objectives, where a MILP cannot be solved in time. The GA only needs a fitness function.

## CVRP

**Q31. State the CVRP objective and constraints.**

min Σ_k Σ_i Σ_j d_ij x_ijk, such that each stop is visited once, routes start and end at the depot, the load per route is within vehicle capacity, route length is at most L_max, and at most K vehicles are used per depot.

**Q32. What is a package and how was demand rounded?**

One package = one forecast order, because the data has no weights. Weekly fractional forecasts are apportioned to whole packages per depot with the largest-remainder method, which preserves the expected total.

**Q33. How were stops larger than vehicle capacity handled?**

They were split into several stops at the same location (split delivery), so the CVRP stays feasible.

## Guided Local Search

**Q34. How does GLS escape local minima?**

At a local minimum it penalises solution features (arcs) with high utility c_a/(1+p_a). The search continues on cost + λ·Σ penalties, so long, frequently used arcs become expensive and the search moves to new regions.

**Q35. What were the routing results?**

In CONUS, GLS used 18.2% less distance than Nearest Neighbor (whose routes also break the route-length limit) and 0.12% less than standard OR-Tools greedy descent.

## Algorithm comparison

**Q36. How much did the CFLP save versus naive placement?**

38.6% lower total cost than random sites in CONUS, with the same number of warehouses and identical data.

**Q37. Did forecasting improve warehouse planning?**

In CONUS, yes: 29.5% lower realised cost than planning on historical averages, over 13 held-out weeks. In Puerto Rico, no: -21.6%, because the unit forecast was biased high and opened an extra warehouse.

## Sensitivity analysis

**Q38. How does the number of warehouses respond to fixed cost?**

Higher fixed costs reduce the number of warehouses opened, and higher transport costs increase it. The cost curve over a forced number of warehouses is U-shaped, with its minimum at the CFLP's choice.

**Q39. What happens if demand grows 20%?**

The robustness experiment keeps the selected warehouses and re-allocates zones. It reports the maximum utilisation and any unserved units or overload; Puerto Rico runs close to capacity and is the first to become infeasible.

## Mathematical optimisation

**Q40. Why use an exact solver and not only heuristics?**

An exact MILP gives a provable optimum or a gap. That benchmark is what lets us quantify the GA's and K-Means' sub-optimality honestly.

**Q41. Why are distances called approximate?**

They are great-circle km × 1.2 circuity, because OSRM was not reachable and coordinates were not sent externally. They are never labelled as road-network distances.

## Research contribution

**Q42. What is the contribution of this project?**

An end-to-end, reproducible forecasting → location → routing pipeline on real order data. It includes honest regime-aware forecasting, exact-versus-heuristic benchmarking with identical inputs, and evidence that forecast bias drives capacity decisions.

**Q43. What are the main limitations?**

Simulated costs and capacities, approximate distances, synthetic destination fields, one package per order, and a short post-break history.

## Computational complexity

**Q44. How long does the full pipeline take?**

Preprocessing ~30 s, forecasting ~7 min (Random Forest/XGBoost grids), CFLP seconds, GA ~1–2 min, and routing ~1.5 min (10 s GLS per depot). The experiments take several minutes.
