"""Performance metrics, cross-module consistency checks and the final performance summary."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import get_path, load_config


def pct_reduction(baseline: float, optimized: float) -> float:
    """((baseline - optimized) / baseline) * 100; NaN when the baseline is zero or missing."""
    try:
        b, o = float(baseline), float(optimized)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(b) or not np.isfinite(o) or abs(b) < 1e-12:
        return float("nan")
    return 100.0 * (b - o) / b


def utilization_pct(used: float, available: float) -> float:
    return float("nan") if not available else 100.0 * used / available


def consistency_checks() -> pd.DataFrame:
    """Validate the written outputs against each other (used by tests and `evaluate`)."""
    out = get_path("outputs_dir")
    al = pd.read_csv(out / "selected_allocation.csv")
    wh = pd.read_csv(out / "selected_warehouses.csv")
    st = pd.read_csv(out / "optimized_delivery_routes.csv")
    va = pd.read_csv(out / "vehicle_assignments.csv")
    demand = pd.read_csv(out / "cflp_zone_demand_forecast.csv")
    rc = load_config()["routing"]["networks"]
    rows = []

    def add(check, ok, detail=""):
        rows.append({"check": check, "passed": bool(ok), "detail": str(detail)})

    nets = load_config()["forecasting"]["networks"]
    expected = set(demand[demand["network"].isin(nets)]["zone_id"])
    add("every demand zone is allocated", set(al["zone_id"]) == expected and (al["warehouse_id"] != "UNSERVED").all(),
        f"{len(al)} rows, {len(expected)} zones")
    open_ids = set(wh[wh["is_open"]]["warehouse_id"])
    add("no closed warehouse serves demand", set(al["warehouse_id"]) <= open_ids)
    load = al.groupby("warehouse_id")["forecast_units_per_week"].sum()
    cap = wh.set_index("warehouse_id")["capacity_units_per_week"]
    add("warehouse capacity respected (units/week)", (load <= cap.reindex(load.index) + 1e-6).all(),
        f"max utilisation {100 * (load / cap.reindex(load.index)).max():.1f}%")
    netmap = al.set_index("zone_id")["network"]
    whnet = wh.set_index("warehouse_id")["network"]
    add("zone and warehouse in the same network", (al["network"].values == whnet.reindex(al["warehouse_id"]).values).all())
    add("vehicle capacity respected", (va["packages"] <= va["vehicle_capacity"]).all(),
        f"max load {va['packages'].max()} / {va['vehicle_capacity'].min()}")
    add("routes start and end at their depot",
        va.apply(lambda r: r["route_sequence"].startswith(r["warehouse_id"]) and r["route_sequence"].endswith(r["warehouse_id"]), axis=1).all())
    zone_wh = al.set_index("zone_id")["warehouse_id"]
    add("each stop is routed from the warehouse its zone is allocated to",
        (st["warehouse_id"].values == zone_wh.reindex(st["zone_id"]).values).all())
    add("stop network equals route network (no mainland-island routes)",
        (st["network"].values == netmap.reindex(st["zone_id"]).values).all())
    add("no stop visited twice", not st.duplicated(["network", "stop_id"]).any())
    for net in nets:
        expected_pk = int(sum(round(g["forecast_orders_per_week"].sum()) for _, g in
                              al[al["network"] == net].groupby("warehouse_id")))
        add(f"{net}: all forecast packages routed (largest-remainder rounding per depot)",
            st[st["network"] == net]["packages"].sum() == expected_pk, f"{st[st['network'] == net]['packages'].sum()} vs {expected_pk}")
        mx = rc[net]["max_route_km"]
        add(f"{net}: route length <= {mx} km", (va[va["network"] == net]["distance_km"] <= mx + 1e-6).all())
    # cost recomputation
    c = load_config()["optimization"]["networks"]
    res = pd.read_csv(out / "warehouse_optimization_results.csv").set_index("network")
    for net in nets:
        a = al[al["network"] == net]
        transport = (a["road_km_approx"] * a["forecast_orders_per_week"] * c[net]["cost_per_order_km"]).sum()
        opening = len(wh[(wh["network"] == net) & wh["is_open"]]) * c[net]["fixed_cost_per_week"]
        sel = res.loc[net] if a["solution"].iat[0] == "CFLP" else None
        detail = f"transport {transport:.2f}, opening {opening:.0f}"
        ok = True if sel is None else (abs(sel["transport_cost"] - transport) < 1e-4 and abs(sel["opening_cost"] - opening) < 1e-6)
        add(f"{net}: transport/opening cost recomputed from allocation", ok, detail)
    return pd.DataFrame(rows)


def final_summary() -> pd.DataFrame:
    """Headline KPIs with provenance: actual (dataset), forecast (Phase 3) or simulated (assumptions)."""
    out = get_path("outputs_dir")
    P = load_config()["optimization"]["periods_per_year"]
    rows = []

    def add(section, network, metric, value, unit, source, baseline=None, improvement_pct=None):
        rows.append({"section": section, "network": network, "metric": metric, "value": value, "unit": unit,
                     "source": source, "baseline": baseline, "improvement_pct": improvement_pct})

    eda = pd.read_csv(out / "eda_summary.csv")
    gv = lambda scope, m: eda[(eda["scope"] == scope) & (eda["metric"] == m)]["value"].iat[0]
    add("data", "ALL", "raw order-item rows", gv("raw", "order-item rows"), "rows", "actual")
    add("data", "ALL", "orders in demand set", gv("demand set", "orders (deliveries)"), "orders", "actual")
    add("data", "ALL", "units in demand set", gv("demand set", "units"), "units", "actual")
    d = pd.read_csv(out / "cflp_zone_demand_forecast.csv")
    for net, g in d.groupby("network"):
        add("forecast", net, "demand zones", len(g), "zones", "actual")
        add("forecast", net, "forecast orders per week", g["forecast_per_period_orders"].sum(), "orders/week", "forecast")
        add("forecast", net, "forecast units per week", g["forecast_per_period_units"].sum(), "units/week", "forecast")
    sel = pd.read_csv(out / "selected_forecast_model.csv")
    for r in sel.itertuples():
        add("forecast", r.network, f"{r.target} model", f"{r.model} ({r.handling})", "", "forecast")
        add("forecast", r.network, f"{r.target} zone-total WAPE (13 held-out weeks)", r.WAPE, "ratio", "forecast")
    wc = pd.read_csv(out / "experiment_warehouse_comparison.csv")
    for net, g in wc.groupby("network", sort=False):
        c = g[g["method"].str.startswith("CFLP")].iloc[0]
        add("warehouse", net, "warehouses opened", c["n_open"], "warehouses", "simulated")
        add("warehouse", net, "opening cost per week", c["opening_cost"], "USD/week", "simulated")
        add("warehouse", net, "transport cost per week", c["transport_cost"], "USD/week", "simulated")
        add("warehouse", net, "total CFLP cost per week (incl. handling)", c["total_cost"], "USD/week", "simulated")
        add("warehouse", net, "mean warehouse utilisation", 100 * c["mean_utilization"], "%", "simulated")
        for base in ["Random", "K-Means", "Genetic"]:
            b = g[g["method"].str.startswith(base)]
            if len(b):
                add("warehouse", net, f"CFLP vs {base}: total cost", c["total_cost"], "USD/week", "simulated",
                    b["total_cost"].iat[0], pct_reduction(b["total_cost"].iat[0], c["total_cost"]))
    rc = pd.read_csv(out / "experiment_routing_comparison.csv")
    for net, g in rc.groupby("network", sort=False):
        gl = g[g["method"] == "ortools_gls"].iloc[0]
        add("routing", net, "vehicles used (GLS)", gl["vehicles"], "vehicles", "simulated")
        add("routing", net, "total route distance per week (GLS)", gl["total_distance_km"], "approx road km", "simulated")
        add("routing", net, "total route duration per week (GLS)", gl["total_duration_h"], "hours", "simulated")
        add("routing", net, "routing cost per week (GLS)", gl["total_route_cost"], "USD/week", "simulated")
        for base in ["nearest_neighbor", "ortools_standard"]:
            b = g[g["method"] == base].iloc[0]
            add("routing", net, f"GLS vs {base}: distance", gl["total_distance_km"], "km", "simulated",
                b["total_distance_km"], pct_reduction(b["total_distance_km"], gl["total_distance_km"]))
    res = pd.read_csv(out / "warehouse_optimization_results.csv").set_index("network")
    for net, g in rc.groupby("network", sort=False):
        gl = g[g["method"] == "ortools_gls"].iloc[0]
        tot = res.loc[net, "opening_cost"] + res.loc[net, "handling_cost"] + gl["total_route_cost"]
        add("operating cost", net, "estimated operating cost per week (warehouses + handling + routes)", tot, "USD/week", "simulated")
        add("operating cost", net, "estimated operating cost per year", tot * P, "USD/year", "simulated")
    fi = pd.read_csv(out / "forecast_impact_comparison.csv")
    for net, g in fi.groupby("network", sort=False):
        h, f = g.iloc[0], g.iloc[1]
        add("forecast impact", net, "realised weekly cost: forecast plan vs historical plan", f["realised_total_cost"],
            "USD/week", "simulated", h["realised_total_cost"], pct_reduction(h["realised_total_cost"], f["realised_total_cost"]))
    df = pd.DataFrame(rows)
    df.to_csv(out / "final_performance_summary.csv", index=False)
    return df
