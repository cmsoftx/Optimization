"""Figures for Phases 4-8 (static matplotlib + interactive folium maps)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import get_path
from .visualization import INK, MUTED, NET_COLORS, _geo_aspect, _save, plt  # shared style

CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
NETS = ["CONUS", "Puerto Rico"]
OUT = get_path("outputs_dir")


def _wh_colors(ids) -> dict:
    ids = list(dict.fromkeys(ids))
    return {w: CAT[i] if i < len(CAT) else "#52514e" for i, w in enumerate(ids)}


def fig_candidates(demand: pd.DataFrame, cands: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [2.2, 1]})
    src_col = {"coverage": CAT[0], "demand": CAT[1], "coverage+demand": CAT[2]}
    for ax, net in zip(axes, NETS):
        z = demand[demand["network"] == net]
        ax.scatter(z["centroid_lon"], z["centroid_lat"], s=8 + 60 * np.sqrt(z["forecast_per_period_orders"] / z["forecast_per_period_orders"].max()),
                   color="#c9c8c3", alpha=0.7, label="demand zone (size = forecast orders)")
        c = cands[cands["network"] == net]
        for s, g in c.groupby("source"):
            lab = "all zones are candidates" if net == "Puerto Rico" else s
            ax.scatter(g["centroid_lon"], g["centroid_lat"], marker="^", s=70, color=src_col.get(s, INK),
                       edgecolor="white", linewidth=0.8, label=f"candidate: {lab} ({len(g)})")
        _geo_aspect(ax, z["centroid_lat"].mean())
        ax.set_title(f"{net}: {len(c)} candidate sites from {len(z)} zones", fontsize=10)
        ax.legend(fontsize=7, loc="lower left")
    fig.suptitle("Candidate warehouse sites: demand-weighted coverage clusters + highest-demand zones", fontweight="bold")
    return _save(fig, "phase4_candidate_warehouses.png")


def fig_allocation(alloc: pd.DataFrame, wh: pd.DataFrame, name: str = "phase4_selected_allocation.png",
                   title: str = "CFLP solution") -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2), gridspec_kw={"width_ratios": [2.2, 1]})
    for ax, net in zip(axes, NETS):
        a = alloc[alloc["network"] == net]
        w = wh[(wh["network"] == net) & wh["is_open"]]
        col = _wh_colors(w["warehouse_id"])
        for r in a.itertuples():
            ax.plot([r.zone_lon, r.warehouse_lon], [r.zone_lat, r.warehouse_lat], color=col.get(r.warehouse_id, MUTED),
                    lw=0.6, alpha=0.45)
        ax.scatter(a["zone_lon"], a["zone_lat"], s=8 + 70 * np.sqrt(a["forecast_orders_per_week"] / a["forecast_orders_per_week"].max()),
                   c=[col.get(x, MUTED) for x in a["warehouse_id"]], alpha=0.75, edgecolor="white", linewidth=0.4)
        for k, r in enumerate(w.itertuples()):
            ax.scatter(r.centroid_lon, r.centroid_lat, marker="*", s=380, color=col[r.warehouse_id], edgecolor=INK, linewidth=1, zorder=5)
            ax.annotate(f"{r.warehouse_id}\n{r.dominant_city} ({r.utilization_pct:.0f}%)", (r.centroid_lon, r.centroid_lat),
                        xytext=(7, 6 if k % 2 == 0 else -26), textcoords="offset points", fontsize=7.5)
        _geo_aspect(ax, a["zone_lat"].mean())
        ax.set_title(f"{net}: {len(w)} warehouses, {len(a)} zones allocated", fontsize=10)
    fig.suptitle(f"{title}: selected warehouses (★, % = capacity utilisation) and zone allocation", fontweight="bold")
    return _save(fig, name)


def fig_utilization(wh: pd.DataFrame) -> Path:
    w = wh[wh["is_open"]].sort_values(["network", "utilization_pct"])
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(w) + 1.5))
    y = np.arange(len(w))
    ax.barh(y, w["utilization_pct"], color=[NET_COLORS[n] for n in w["network"]], height=0.7)
    for yi, (u, cap, used) in enumerate(zip(w["utilization_pct"], w["capacity_units_per_week"], w["assigned_units_per_week"])):
        ax.text(u + 1, yi, f"{u:.0f}%  ({used:.1f} / {cap:.0f} units/wk)", va="center", fontsize=7.5, color=MUTED)
    ax.set_yticks(y, [f"{a} {b}" for a, b in zip(w["warehouse_id"], w["dominant_city"])], fontsize=8)
    ax.axvline(100, color=INK, lw=1, ls="--")
    ax.set_xlim(0, 125); ax.set_xlabel("capacity utilisation (%)")
    ax.set_title("Warehouse capacity utilisation (blue = CONUS, orange = Puerto Rico)")
    return _save(fig, "phase4_warehouse_utilization.png")


def fig_cost_breakdown(res: pd.DataFrame) -> Path:
    r = res[res["network"].isin(NETS)].set_index("network")
    fig, ax = plt.subplots(figsize=(9, 2.8))
    left = np.zeros(len(r))
    for k, (c, lab) in enumerate([("opening_cost", "warehouse opening (fixed)"), ("transport_cost", "transport"),
                                  ("handling_cost", "handling")]):
        ax.barh(r.index, r[c], left=left, color=CAT[k], height=0.55, label=lab, edgecolor="#fcfcfb", linewidth=2)
        for yi, (l, v) in enumerate(zip(left, r[c])):
            if v / r["total_cost"].iat[yi] > 0.06:
                ax.text(l + v / 2, yi, f"${v:,.0f}", ha="center", va="center", color="white", fontsize=8)
        left += r[c].to_numpy()
    for yi, t in enumerate(r["total_cost"]):
        ax.text(t * 1.01, yi, f"${t:,.0f}/wk", va="center", fontsize=8)
    ax.set_xlabel("USD per week (simulated cost assumptions)"); ax.legend(fontsize=8, ncol=3, loc="lower right")
    ax.set_title("CFLP cost breakdown per network"); ax.set_xlim(0, r["total_cost"].max() * 1.18)
    return _save(fig, "phase4_cost_breakdown.png")


def fig_distance(alloc: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    for ax, net in zip(axes, NETS):
        a = alloc[alloc["network"] == net]
        bins = np.linspace(0, max(a["road_km_approx"].max(), 1), 25)
        ax.hist(a["road_km_approx"], bins=bins, weights=a["forecast_orders_per_week"], color=NET_COLORS[net], rwidth=0.9)
        m = np.average(a["road_km_approx"], weights=a["forecast_orders_per_week"])
        ax.axvline(m, color=INK, ls="--", lw=1)
        ax.text(m, ax.get_ylim()[1] * 0.92, f"  order-weighted mean {m:.0f} km", fontsize=8)
        ax.set_xlabel("zone → warehouse approx. road km"); ax.set_ylabel("forecast orders / week")
        ax.set_title(net)
    fig.suptitle("Customer-to-warehouse distance (orders-weighted)", fontweight="bold")
    return _save(fig, "phase4_customer_distance.png")


def folium_allocation(alloc: pd.DataFrame, wh: pd.DataFrame, cands: pd.DataFrame, path: Path | None = None) -> Path:
    import folium

    path = path or get_path("figures_dir") / "phase4_warehouse_allocation_map.html"
    m = folium.Map(location=[33, -88], zoom_start=4, tiles="OpenStreetMap")
    for net in NETS:
        w = wh[(wh["network"] == net) & wh["is_open"]]
        col = _wh_colors(w["warehouse_id"])
        fc = folium.FeatureGroup(name=f"{net}: candidate sites", show=False)
        for r in cands[cands["network"] == net].itertuples():
            folium.CircleMarker([r.centroid_lat, r.centroid_lon], radius=4, color=MUTED, fill=True,
                                tooltip=f"candidate {r.warehouse_id} ({r.dominant_city}) - {r.source}").add_to(fc)
        fc.add_to(m)
        fg = folium.FeatureGroup(name=f"{net}: allocation", show=True)
        a = alloc[alloc["network"] == net]
        for r in a.itertuples():
            c = col.get(r.warehouse_id, MUTED)
            folium.PolyLine([[r.zone_lat, r.zone_lon], [r.warehouse_lat, r.warehouse_lon]], color=c, weight=1, opacity=0.5).add_to(fg)
            folium.CircleMarker([r.zone_lat, r.zone_lon], radius=float(2 + 8 * np.sqrt(r.forecast_orders_per_week / a["forecast_orders_per_week"].max())),
                                color=c, fill=True, fill_opacity=0.7,
                                tooltip=f"{r.zone_id} ({r.zone_city}) → {r.warehouse_id}<br>{r.forecast_orders_per_week:.2f} orders/wk, "
                                        f"{r.forecast_units_per_week:.2f} units/wk<br>{r.road_km_approx:.0f} approx road km").add_to(fg)
        for r in w.itertuples():
            folium.Marker([r.centroid_lat, r.centroid_lon], icon=folium.Icon(color="black", icon="home"),
                          tooltip=(f"<b>{r.warehouse_id}</b> {r.dominant_city}, {r.dominant_state}<br>zones {r.assigned_zones}, "
                                   f"units {r.assigned_units_per_week:.1f}/{r.capacity_units_per_week:.0f} "
                                   f"({r.utilization_pct:.0f}%)<br>fixed ${r.fixed_cost_per_week:,.0f}/wk")).add_to(fg)
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(path))
    return path


def fig_ga_convergence(conv: pd.DataFrame, comp: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    for ax, net in zip(axes, NETS):
        g = conv[conv["network"] == net]
        for k, (seed, h) in enumerate(g.groupby("seed")):
            ax.plot(h["generation"], h["best_so_far"], color=CAT[k % 5], lw=1.6, label=f"seed {seed}")
            ax.plot(h["generation"], h["mean"], color=CAT[k % 5], lw=0.7, alpha=0.35)
        opt = comp[(comp["network"] == net) & comp["method"].str.startswith("CFLP")]["total_cost"].iat[0]
        hand = comp[(comp["network"] == net) & comp["method"].str.startswith("CFLP")]["handling_cost"].iat[0]
        ax.axhline(opt - hand, color=INK, ls="--", lw=1.2, label="CFLP optimum")
        lo = (opt - hand) * 0.98
        ax.set_ylim(lo, min(g["mean"].max(), (opt - hand) * 1.6))
        ax.set_xlabel("generation"); ax.set_ylabel("fitness = opening + transport (USD/wk)")
        ax.set_title(f"{net}: best-so-far (thick) and population mean (thin)", fontsize=10)
        ax.legend(fontsize=7)
    fig.suptitle("Genetic algorithm convergence vs the CFLP optimum", fontweight="bold")
    p = _save(fig, "ga_convergence.png")
    return p


def fig_algorithm_comparison(comp: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for ax, net in zip(axes, NETS):
        g = comp[comp["network"] == net]
        ax.bar(range(len(g)), g["total_cost"], color=CAT[: len(g)], width=0.6)
        for i, (c, gap) in enumerate(zip(g["total_cost"], g["gap_vs_cflp_pct"])):
            ax.text(i, c, f"${c:,.0f}\n(+{gap:.1f}%)" if gap > 1e-9 else f"${c:,.0f}\n(optimal)", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(range(len(g)), [m.replace(" (", "\n(") for m in g["method"]], fontsize=7.5)
        ax.set_ylim(0, g["total_cost"].max() * 1.25); ax.set_ylabel("total cost USD/week")
        ax.set_title(net)
    fig.suptitle("Warehouse location methods on identical data (gap vs CFLP optimum)", fontweight="bold")
    return _save(fig, "phase5_warehouse_algorithm_comparison.png")


def fig_routes_static(routes: pd.DataFrame, stops: pd.DataFrame, net: str, name: str) -> Path:
    s = stops[(stops["network"] == net) & (stops["method"] == "ortools_gls")]
    fig, ax = plt.subplots(figsize=(12 if net == "CONUS" else 8, 6.5))
    col = _wh_colors(s["warehouse_id"].unique())
    styles = ["-", "--", ":", "-."]
    for (wid, vid), g in s.groupby(["warehouse_id", "vehicle_id"]):
        g = g.sort_values("stop_sequence")
        k = int(vid.split("-V")[-1]) - 1
        lon = np.r_[g["depot_lon"].iat[0], g["lon"], g["depot_lon"].iat[0]]
        lat = np.r_[g["depot_lat"].iat[0], g["lat"], g["depot_lat"].iat[0]]
        ax.plot(lon, lat, color=col[wid], lw=1.3, ls=styles[k % 4], alpha=0.85)
        ax.scatter(g["lon"], g["lat"], s=6 + 4 * g["packages"], color=col[wid], edgecolor="white", linewidth=0.4, zorder=3)
    for wid, g in s.groupby("warehouse_id"):
        ax.scatter(g["depot_lon"].iat[0], g["depot_lat"].iat[0], marker="s", s=140, color=col[wid], edgecolor=INK, zorder=5)
        nveh = g["vehicle_id"].nunique()
        ax.annotate(f"{wid} ({nveh} veh)", (g["depot_lon"].iat[0], g["depot_lat"].iat[0]), xytext=(6, 6),
                    textcoords="offset points", fontsize=8)
    _geo_aspect(ax, s["lat"].mean())
    r = routes[(routes["network"] == net) & (routes["method"] == "ortools_gls")]
    ax.set_title(f"{net}: Guided Local Search routes, {r['vehicle_id'].nunique()} vehicles, "
                 f"{r['distance_km'].sum():,.0f} approx road km/week (straight segments drawn; distances use circuity factor)",
                 fontsize=10)
    return _save(fig, name)


def folium_routes(stops: pd.DataFrame, routes: pd.DataFrame, path: Path | None = None) -> Path:
    import folium

    path = path or get_path("figures_dir") / "phase6_delivery_routes_map.html"
    s = stops[stops["method"] == "ortools_gls"]
    m = folium.Map(location=[33, -88], zoom_start=4, tiles="OpenStreetMap")
    rinfo = routes[routes["method"] == "ortools_gls"].set_index("vehicle_id")
    for net in NETS:
        sn = s[s["network"] == net]
        col = _wh_colors(sn["warehouse_id"].unique())
        for wid, gw in sn.groupby("warehouse_id"):
            fg = folium.FeatureGroup(name=f"{net} · {wid}", show=True)
            folium.Marker([gw["depot_lat"].iat[0], gw["depot_lon"].iat[0]], icon=folium.Icon(color="black", icon="home"),
                          tooltip=f"<b>Depot {wid}</b>: {gw['vehicle_id'].nunique()} vehicles").add_to(fg)
            for k, (vid, g) in enumerate(gw.groupby("vehicle_id")):
                g = g.sort_values("stop_sequence")
                pts = [[g["depot_lat"].iat[0], g["depot_lon"].iat[0]]] + g[["lat", "lon"]].values.tolist() + \
                      [[g["depot_lat"].iat[0], g["depot_lon"].iat[0]]]
                ri = rinfo.loc[vid]
                folium.PolyLine(pts, color=col[wid], weight=3, opacity=0.8, dash_array=None if k % 2 == 0 else "8 6",
                                tooltip=f"<b>{vid}</b>: {ri['n_stops']} stops, {ri['packages']}/{ri['vehicle_capacity']} packages, "
                                        f"{ri['distance_km']:.0f} km, {ri['duration_h']:.1f} h").add_to(fg)
                for r in g.itertuples():
                    folium.CircleMarker([r.lat, r.lon], radius=4, color=col[wid], fill=True,
                                        tooltip=f"{vid} stop {r.stop_sequence}: {r.stop_id}, {r.packages} packages").add_to(fg)
            fg.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    m.save(str(path))
    return path


def fig_routing_comparison(comp: pd.DataFrame) -> Path:
    labels = {"nearest_neighbor": "Nearest\nNeighbor", "ortools_standard": "OR-Tools\nstandard", "ortools_gls": "OR-Tools\nGLS"}
    order = ["nearest_neighbor", "ortools_standard", "ortools_gls"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5))
    for i, net in enumerate(NETS):
        g = comp[comp["network"] == net].set_index("method").reindex(order)
        for j, (c, t) in enumerate([("total_distance_km", "distance (approx road km/wk)"), ("vehicles", "vehicles used"),
                                    ("total_duration_h", "route hours / week")]):
            ax = axes[i, j]
            ax.bar(range(3), g[c], color=CAT[:3], width=0.6)
            for k, (v, ok) in enumerate(zip(g[c], g["all_feasible"])):
                ax.text(k, v, f"{v:,.0f}" + ("" if ok else "\ninfeasible"), ha="center", va="bottom", fontsize=8,
                        color=INK if ok else "#e34948")
            ax.set_xticks(range(3), [labels[m] for m in order], fontsize=8)
            ax.set_ylim(0, g[c].max() * 1.28)
            ax.set_title(f"{net}: {t}", fontsize=9.5)
    fig.suptitle("Routing algorithms on identical depots, demand and distance matrices", fontweight="bold")
    return _save(fig, "phase6_routing_comparison.png")


def fig_forecast_impact(fi: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for ax, net in zip(axes, NETS):
        g = fi[fi["network"] == net].reset_index(drop=True)
        lab = ["Historical-avg\nplan", "Forecast\nplan", "Oracle\n(perfect info)"]
        ax.bar(range(3), g["realised_opening_cost"], color=CAT[0], width=0.55, label="opening", edgecolor="#fcfcfb", linewidth=2)
        ax.bar(range(3), g["realised_transport_cost"], bottom=g["realised_opening_cost"], color=CAT[1], width=0.55,
               label="transport", edgecolor="#fcfcfb", linewidth=2)
        for k, r in g.iterrows():
            ax.text(k, r["realised_opening_cost"] + r["realised_transport_cost"],
                    f"{r['warehouses_opened']} WH\nregret {r['regret_vs_oracle_pct']:.1f}%", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(range(3), lab); ax.set_ylabel("realised cost USD/wk (excl. handling)")
        ax.set_ylim(0, (g["realised_opening_cost"] + g["realised_transport_cost"]).max() * 1.3)
        ax.set_title(f"{net}: plans evaluated on the same 13 held-out weeks", fontsize=10)
        ax.legend(fontsize=8)
    fig.suptitle("Experiment C: does demand forecasting improve warehouse planning?", fontweight="bold")
    return _save(fig, "phase8_forecast_impact.png")


def fig_sensitivity(sens: pd.DataFrame) -> Path:
    w = sens[sens["experiment"] == "warehouse"]
    params = [("capacity_multiplier", "capacity × base"), ("fixed_warehouse_count", "warehouses (forced)"),
              ("fixed_cost_multiplier", "fixed cost × base"), ("cost_per_km_multiplier", "cost/km × base"),
              ("demand_growth", "demand growth"), ("zone_diameter_km", "zone diameter km (CONUS)")]
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.5))
    for ax, (p, lab) in zip(axes.ravel(), params):
        for net in NETS:
            g = w[(w["parameter"] == p) & (w["network"] == net)].sort_values("value")
            if g.empty:
                continue
            ax.plot(g["value"], g["total_cost"], color=NET_COLORS[net], marker="o", label=net)
            for r in g.itertuples():
                ax.annotate(f"{r.n_open}" + ("" if r.feasible else "✗"), (r.value, r.total_cost), xytext=(0, 6),
                            textcoords="offset points", ha="center", fontsize=7.5, color=NET_COLORS[net])
        ax.set_xlabel(lab); ax.set_ylabel("total cost USD/wk")
        ax.set_title(f"{lab}", fontsize=10)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Experiment D: CFLP sensitivity (labels = warehouses opened; ✗ = infeasible / unserved demand)",
                 fontweight="bold")
    return _save(fig, "phase8_sensitivity_warehouse.png")


def fig_sensitivity_routing(sens: pd.DataFrame) -> Path:
    r = sens[sens["experiment"] == "routing"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for ax, (p, lab) in zip(axes, [("vehicle_capacity", "vehicle capacity (packages)"), ("vehicles_per_depot", "vehicles per depot")]):
        for net in NETS:
            g = r[(r["parameter"] == p) & (r["network"] == net)].sort_values("value")
            ax.plot(g["value"], g["total_distance_km"], color=NET_COLORS[net], marker="o", label=net)
            for x in g.itertuples():
                ax.annotate(f"{int(x.vehicles)}v" + ("" if x.feasible else " ✗"), (x.value, x.total_distance_km), xytext=(0, 6),
                            textcoords="offset points", ha="center", fontsize=7.5, color=NET_COLORS[net])
        ax.set_yscale("log"); ax.set_xlabel(lab); ax.set_ylabel("route km / week (log)")
        ax.legend(fontsize=8)
    fig.suptitle("Experiment D: routing sensitivity (labels = vehicles used; ✗ = unserved stops or violations)", fontweight="bold")
    return _save(fig, "phase8_sensitivity_routing.png")


def fig_robustness(rb: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for net in NETS:
        g = rb[rb["network"] == net].sort_values("demand_change")
        x = 100 * g["demand_change"]
        axes[0].plot(x, g["total_operating_cost"], marker="o", color=NET_COLORS[net], label=net)
        axes[1].plot(x, 100 * g["reallocated_max_utilization"], marker="o", color=NET_COLORS[net], label=net)
        axes[2].plot(x, g["unserved_units"], marker="o", color=NET_COLORS[net], label=f"{net}: unserved units")
        axes[2].plot(x, g["capacity_overload_if_allocation_kept"], marker="s", ls="--", color=NET_COLORS[net],
                     label=f"{net}: overload if allocation kept")
    axes[0].set_ylabel("USD/wk"); axes[0].set_title("operating cost (warehouses + handling + transport + routes)", fontsize=9.5)
    axes[1].axhline(100, color=INK, ls="--", lw=1); axes[1].set_ylabel("%"); axes[1].set_title("max warehouse utilisation (re-allocated)", fontsize=9.5)
    axes[2].set_ylabel("units/week"); axes[2].set_title("infeasibility under demand shocks", fontsize=9.5)
    for ax in axes:
        ax.set_xlabel("demand change (%)"); ax.legend(fontsize=7)
    fig.suptitle("Experiment E: robustness of the selected warehouse + route plan", fontweight="bold")
    return _save(fig, "phase8_robustness.png")
