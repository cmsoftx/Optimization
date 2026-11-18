"""Streamlit dashboard: demand-driven warehouse location and vehicle routing.

Run from the project root:  streamlit run dashboard/app.py
Every figure is read from the pipeline outputs (data/outputs) or computed live by the what-if page.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import load_config  # noqa: E402

OUT = ROOT / "data" / "outputs"
FIG = ROOT / "reports" / "figures"
NET_COLORS = {"CONUS": "#2a78d6", "Puerto Rico": "#eb6834", "Hawaii": "#1baf7a"}
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
METHOD_LABEL = {"nearest_neighbor": "Nearest Neighbor", "ortools_standard": "OR-Tools standard",
                "ortools_gls": "OR-Tools Guided Local Search"}
SOURCE_BADGE = {"actual": "🟦 Actual (dataset)", "forecast": "🟧 Forecast (Phase 3)", "simulated": "🟩 Simulated (assumptions)"}

st.set_page_config(page_title="Warehouse & Route Optimisation", page_icon="📦", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1400px;}
div[data-testid="stMetric"] {background: #ffffff; border: 1px solid #e4e3df; border-radius: 10px; padding: 10px 14px;}
div[data-testid="stMetricLabel"] p {font-size: 0.82rem; color: #52514e;}
h1, h2, h3 {letter-spacing: -0.01em;}
.badge {display:inline-block; padding:2px 8px; border-radius:6px; font-size:0.75rem; background:#f2f1ee; color:#52514e;}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load(name: str, parse_dates: tuple = ()) -> pd.DataFrame | None:
    p = OUT / name
    if not p.exists():
        return None
    return pd.read_csv(p, parse_dates=list(parse_dates) or None, low_memory=False)


def need(*names: str) -> bool:
    missing = [n for n in names if load(n) is None]
    if missing:
        st.warning(f"Missing outputs: {', '.join(missing)}. Run `python main.py all` from the project root.")
        return False
    return True


def badge(source: str) -> None:
    st.caption(SOURCE_BADGE[source])


def layout_fig(fig, height=380):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), font=dict(size=12))
    return fig


def zone_map(df, lat, lon, size, color, hover, center, zoom, height=520, color_map=None, lines=None, title=None):
    fig = go.Figure()
    if lines is not None:
        for c, g in lines.groupby("color"):
            lat_l, lon_l = [], []
            for r in g.itertuples():
                lat_l += [r.lat0, r.lat1, None]; lon_l += [r.lon0, r.lon1, None]
            fig.add_trace(go.Scattermap(lat=lat_l, lon=lon_l, mode="lines", line=dict(width=1, color=c), opacity=0.5,
                                        hoverinfo="skip", showlegend=False))
    for key, g in df.groupby(color):
        fig.add_trace(go.Scattermap(lat=g[lat], lon=g[lon], mode="markers", name=str(key),
                                    marker=dict(size=g[size], color=(color_map or {}).get(key, "#52514e"), opacity=0.75),
                                    text=g[hover], hoverinfo="text"))
    fig.update_layout(map=dict(style="open-street-map", center=center, zoom=zoom), height=height,
                      margin=dict(l=0, r=0, t=30 if title else 0, b=0), title=title,
                      legend=dict(orientation="h", y=1.0, x=0, bgcolor="rgba(255,255,255,0.8)"))
    return fig


VIEW = {"CONUS": (dict(lat=38, lon=-96), 3.0), "Puerto Rico": (dict(lat=18.22, lon=-66.4), 8.0)}


def page_overview():
    st.title("Demand-Driven Warehouse Location & Multi-Vehicle Route Optimisation")
    st.write("An end-to-end system built on the DataCo Smart Supply Chain dataset. It forecasts zone demand, decides where "
             "to open warehouses (CFLP solved exactly with Pyomo + CBC, compared with a Genetic Algorithm, K-Means and "
             "random selection), allocates demand zones within capacity, and routes delivery vehicles (CVRP with OR-Tools "
             "Guided Local Search, compared with Nearest Neighbor and standard OR-Tools search).")
    if not need("eda_summary.csv", "final_performance_summary.csv", "cflp_zone_demand_forecast.csv"):
        return
    s = load("final_performance_summary.csv")
    g = lambda net, metric: s[(s["network"] == net) & (s["metric"] == metric)]["value"].iat[0]
    st.subheader("Dataset")
    badge("actual")
    c = st.columns(4)
    c[0].metric("Order-item rows", f"{int(float(g('ALL', 'raw order-item rows'))):,}")
    c[1].metric("Orders (deliveries) in demand set", f"{int(float(g('ALL', 'orders in demand set'))):,}")
    c[2].metric("Units in demand set", f"{int(float(g('ALL', 'units in demand set'))):,}")
    d = load("cflp_zone_demand_forecast.csv")
    c[3].metric("Demand zones (CONUS + PR)", f"{len(d)}")
    for net in ["CONUS", "Puerto Rico"]:
        st.subheader(net)
        cols = st.columns(6)
        cols[0].metric("Forecast orders / week", f"{float(g(net, 'forecast orders per week')):,.1f}")
        cols[1].metric("Forecast units / week", f"{float(g(net, 'forecast units per week')):,.1f}")
        cols[2].metric("Warehouses opened", f"{int(float(g(net, 'warehouses opened')))}")
        cols[3].metric("Vehicles (GLS)", f"{int(float(g(net, 'vehicles used (GLS)')))}")
        cols[4].metric("Route km / week", f"{float(g(net, 'total route distance per week (GLS)')):,.0f}")
        cols[5].metric("Operating cost / week", f"${float(g(net, 'estimated operating cost per week (warehouses + handling + routes)')):,.0f}")
        st.caption("🟧 demand values are forecasts · 🟩 warehouses, vehicles, distances and costs are simulated from "
                   "documented assumptions in config.yaml · distances are approximate road km (great-circle × 1.2)")
    st.subheader("Optimisation performance")
    imp = s[s["improvement_pct"].notna()][["network", "metric", "baseline", "value", "improvement_pct"]].copy()
    imp["improvement_pct"] = imp["improvement_pct"].astype(float).round(2)
    st.dataframe(imp, hide_index=True, use_container_width=True)
    st.subheader("Workflow")
    st.markdown("**Raw data → cleaning → demand zones → forecasting → candidate sites → CFLP → GA comparison → "
                "warehouse selection → allocation → CVRP → Guided Local Search → evaluation → dashboard & reports**")


def page_analytics():
    st.title("Data analytics")
    badge("actual")
    if not need("eda_monthly_demand_by_network.csv", "eda_weekly_demand_by_network.csv", "demand_zones.csv"):
        return
    m = load("eda_monthly_demand_by_network.csv")
    net_sel = st.multiselect("Networks", ["CONUS", "Puerto Rico", "Hawaii"], default=["CONUS", "Puerto Rico"])
    mm = m[m["network"].isin(net_sel)]
    c1, c2 = st.columns(2)
    for col, y, t in [(c1, "orders", "Orders per month"), (c2, "units", "Units per month")]:
        fig = px.line(mm, x="month", y=y, color="network", color_discrete_map=NET_COLORS, markers=True, title=t)
        fig.add_vline(x="2017-10", line_dash="dash", line_color="#52514e")
        col.plotly_chart(layout_fig(fig), use_container_width=True)
    st.info("**October 2017 structural break:** orders per day rise, while units per order fall from about 6.5 to "
            "about 1. Customers are almost entirely new and the product mix changes. Puerto Rico demand also relocates "
            "about 35 km east (Phase 3).")
    w = load("eda_weekly_demand_by_network.csv")
    w = w[~w["partial_week"] & w["network"].isin(net_sel)]
    fig = px.line(w, x="week_start", y="orders", color="network", color_discrete_map=NET_COLORS, title="Weekly orders")
    st.plotly_chart(layout_fig(fig, 320), use_container_width=True)
    st.subheader("Geographic demand distribution")
    z = load("demand_zones.csv")
    net = st.radio("Map network", ["CONUS", "Puerto Rico"], horizontal=True)
    zz = z[z["network"] == net].copy()
    zz["size"] = 5 + 30 * np.sqrt(zz["units"] / zz["units"].max())
    zz["hover"] = zz["zone_id"] + " · " + zz["dominant_city"] + "<br>orders " + zz["n_orders"].astype(str) + ", units " + zz["units"].astype(str)
    center, zoom = VIEW[net]
    st.plotly_chart(zone_map(zz, "centroid_lat", "centroid_lon", "size", "network", "hover", center, zoom,
                             color_map=NET_COLORS), use_container_width=True)
    c1, c2 = st.columns(2)
    conc = load("eda_zone_concentration.csv")
    if conc is not None:
        fig = px.line(conc, x="zone_share_cum", y="units_share_cum", color="network", color_discrete_map=NET_COLORS,
                      title="Demand concentration (share of zones vs share of units)")
        c1.plotly_chart(layout_fig(fig), use_container_width=True)
    rc = load("eda_regime_comparison.csv")
    if rc is not None:
        c2.markdown("**Before vs after the break**")
        c2.dataframe(rc[["network", "regime", "orders_per_day", "units_per_order", "items_per_order", "customers",
                         "top_category"]].round(2), hide_index=True, use_container_width=True)
    hl = load("eda_high_low_demand_zones.csv")
    if hl is not None:
        st.markdown("**High- and low-demand zones**")
        st.dataframe(hl[hl["network"] == net], hide_index=True, use_container_width=True)


def page_forecast():
    st.title("Demand forecasting")
    badge("forecast")
    if not need("forecast_evaluation.csv", "selected_forecast_model.csv", "cflp_zone_demand_forecast.csv"):
        return
    sel = load("selected_forecast_model.csv")
    st.markdown("**Selected models** (lowest zone-total WAPE over the 13 held-out post-break weeks, per target and network). "
                "XGBoost is not selected for any target or network. Simpler regime-aware methods were more accurate.")
    st.dataframe(sel[["target", "network", "model", "handling", "WAPE", "MAE", "RMSE", "bias_pct"]].round(3),
                 hide_index=True, use_container_width=True)
    c1, c2, c3 = st.columns(3)
    target = c1.selectbox("Target", ["orders", "units"])
    net = c2.selectbox("Network", ["CONUS", "Puerto Rico"])
    eset = c3.selectbox("Evaluation window", ["pre_break_test", "post_break_test", "post_break_adapted"])
    preds = load("order_demand_predictions.csv" if target == "orders" else "unit_demand_predictions.csv",
                 ("period_start",))
    if preds is None:
        preds = load("demand_predictions.csv", ("period_start",))
        st.caption("Full per-model predictions are not available locally; showing the selected model only.")
    p = preds[(preds["granularity"] == "W") & (preds["target"] == target) & (preds["network"] == net) & (preds["eval_set"] == eset)]
    if len(p):
        agg = p.groupby(["model", "handling", "mode", "period_start"])[["actual", "predicted"]].sum().reset_index()
        agg["series"] = agg["model"] + " [" + agg["handling"] + ", " + agg["mode"] + "]"
        act = agg.drop_duplicates("period_start")[["period_start", "actual"]]
        fig = go.Figure(go.Scatter(x=act["period_start"], y=act["actual"], name="Actual", line=dict(color="#0b0b0b", width=3)))
        opts = sorted(agg["series"].unique())
        show = st.multiselect("Series", opts, default=[o for o in opts if "oracle" not in o][:4])
        for k, sname in enumerate(show):
            g = agg[agg["series"] == sname]
            fig.add_trace(go.Scatter(x=g["period_start"], y=g["predicted"], name=sname, line=dict(color=CAT[k % 8])))
        fig.update_layout(title=f"{net}: weekly {target}, network total, actual vs predicted")
        st.plotly_chart(layout_fig(fig, 420), use_container_width=True)
    e = load("forecast_evaluation.csv")
    x = e[(e["granularity"] == "W") & (e["eval_set"] == eset) & (e["target"] == target) & (e["network"] == net)
          & (e["tier"] == "all") & e["level"].isin(["zone_period", "zone_total"])]
    st.markdown("**Error metrics** (zone_period = per zone-week; zone_total = per zone over the window)")
    st.dataframe(x[["level", "mode", "handling", "model", "MAE", "RMSE", "WAPE", "bias_pct"]].sort_values(["level", "WAPE"]).round(3),
                 hide_index=True, use_container_width=True)
    st.subheader("Zone-level forecast handed to the CFLP")
    d = load("cflp_zone_demand_forecast.csv")
    dd = d[d["network"] == net].copy()
    col = "forecast_per_period_orders" if target == "orders" else "forecast_per_period_units"
    dd["size"] = 5 + 30 * np.sqrt(dd[col] / dd[col].max())
    dd["hover"] = dd["zone_id"] + " " + dd["dominant_city"] + "<br>" + target + "/week: " + dd[col].round(2).astype(str)
    center, zoom = VIEW[net]
    st.plotly_chart(zone_map(dd, "centroid_lat", "centroid_lon", "size", "network", "hover", center, zoom, 440,
                             color_map=NET_COLORS), use_container_width=True)
    st.caption(f"Forecast period {d['forecast_start'].iat[0]} → {d['forecast_end'].iat[0]} (13 weeks).")


def _warehouse_map(al, wh, cands, net, show_cands=True, height=560):
    a = al[al["network"] == net].copy()
    w = wh[(wh["network"] == net) & wh["is_open"]]
    colors = {wid: CAT[i % 8] for i, wid in enumerate(w["warehouse_id"])}
    a["size"] = 5 + 22 * np.sqrt(a["forecast_orders_per_week"] / max(a["forecast_orders_per_week"].max(), 1e-9))
    a["hover"] = (a["zone_id"] + " " + a["zone_city"] + " → " + a["warehouse_id"] + "<br>" + a["forecast_orders_per_week"].round(2).astype(str)
                  + " orders/wk, " + a["road_km_approx"].round(0).astype(str) + " km")
    lines = pd.DataFrame({"lat0": a["zone_lat"], "lon0": a["zone_lon"], "lat1": a["warehouse_lat"], "lon1": a["warehouse_lon"],
                          "color": a["warehouse_id"].map(colors).fillna("#52514e")})
    center, zoom = VIEW[net]
    fig = zone_map(a, "zone_lat", "zone_lon", "size", "warehouse_id", "hover", center, zoom, height, colors, lines)
    if show_cands and cands is not None:
        c = cands[cands["network"] == net]
        fig.add_trace(go.Scattermap(lat=c["centroid_lat"], lon=c["centroid_lon"], mode="markers", name="candidate site",
                                    marker=dict(size=9, color="#52514e", symbol="circle", opacity=0.5),
                                    text=c["warehouse_id"] + " " + c["dominant_city"], hoverinfo="text"))
    fig.add_trace(go.Scattermap(lat=w["centroid_lat"], lon=w["centroid_lon"], mode="markers+text", name="open warehouse",
                                marker=dict(size=22, color="#0b0b0b"), text=w["warehouse_id"], textposition="top right",
                                hovertext=w["warehouse_id"] + " " + w["dominant_city"] + "<br>utilisation " + w["utilization_pct"].round(1).astype(str) + "%",
                                hoverinfo="text"))
    return fig


def page_warehouse():
    st.title("Warehouse location optimisation (CFLP)")
    badge("simulated")
    if not need("selected_allocation.csv", "selected_warehouses.csv", "warehouse_algorithm_comparison.csv",
                "candidate_warehouses.csv", "cflp_solver_report.csv"):
        return
    st.latex(r"\min \sum_j F_jY_j+\sum_i\sum_j c_{km}\,d_{ij}\,o_i\,X_{ij}\quad\text{s.t.}\ \sum_j X_{ij}=1,\ "
             r"\sum_i u_iX_{ij}\le Q_jY_j,\ X_{ij}\le Y_j,\ p_{min}\le\sum_jY_j\le p_{max}")
    st.caption("o_i = forecast orders/week (drives transport cost); u_i = forecast units/week (consumes capacity). "
               "CONUS and Puerto Rico are separate models, so no assignment crosses the sea.")
    net = st.radio("Network", ["CONUS", "Puerto Rico"], horizontal=True)
    al, wh, cands = load("selected_allocation.csv"), load("selected_warehouses.csv"), load("candidate_warehouses.csv")
    comp = load("warehouse_algorithm_comparison.csv")
    c = comp[(comp["network"] == net) & comp["method"].str.startswith("CFLP")].iloc[0]
    k = st.columns(5)
    k[0].metric("Warehouses opened", int(c["n_open"]))
    k[1].metric("Opening cost / wk", f"${c['opening_cost']:,.0f}")
    k[2].metric("Transport cost / wk", f"${c['transport_cost']:,.0f}")
    k[3].metric("Total objective / wk", f"${c['total_cost']:,.0f}")
    k[4].metric("Mean utilisation", f"{100 * c['mean_utilization']:.1f}%")
    show = st.checkbox("Show candidate sites", value=True)
    st.plotly_chart(_warehouse_map(al, wh, cands, net, show), use_container_width=True)
    w = wh[(wh["network"] == net) & wh["is_open"]]
    c1, c2 = st.columns([1.2, 1])
    fig = px.bar(w, x="warehouse_id", y="utilization_pct", text=w["utilization_pct"].round(1), color_discrete_sequence=[NET_COLORS[net]],
                 hover_data=["dominant_city", "assigned_zones", "assigned_units_per_week", "capacity_units_per_week"],
                 title="Capacity utilisation (%)")
    fig.add_hline(y=100, line_dash="dash")
    c1.plotly_chart(layout_fig(fig), use_container_width=True)
    pick = c2.selectbox("Warehouse details", w["warehouse_id"])
    r = w[w["warehouse_id"] == pick].iloc[0]
    c2.markdown(f"**{pick}**: {r['dominant_city']}, {r['dominant_state']}  \n"
                f"Assigned zones: {int(r['assigned_zones'])}  \nOrders/week: {r['assigned_orders_per_week']:.1f}  \n"
                f"Units/week: {r['assigned_units_per_week']:.1f} of {r['capacity_units_per_week']:.0f}  \n"
                f"Unused capacity: {r['unused_capacity_units']:.1f} units  \nTransport cost: ${r['transport_cost_per_week']:,.0f}/wk  \n"
                f"Candidate source: {r['source']}")
    st.subheader("CFLP vs Genetic Algorithm vs baselines")
    st.dataframe(comp[comp["network"] == net][["method", "n_open", "total_cost", "opening_cost", "transport_cost",
                                                "avg_distance_km_order_weighted", "mean_utilization", "unserved_units",
                                                "feasible", "gap_vs_cflp_pct", "runtime_s"]].round(3), hide_index=True,
                 use_container_width=True)
    st.dataframe(load("cflp_solver_report.csv"), hide_index=True, use_container_width=True)


def _route_map(stops, net, depots=None, height=600):
    s = stops[stops["network"] == net]
    if depots:
        s = s[s["warehouse_id"].isin(depots)]
    colors = {w: CAT[i % 8] for i, w in enumerate(sorted(s["warehouse_id"].unique()))}
    fig = go.Figure()
    for (wid, vid), g in s.groupby(["warehouse_id", "vehicle_id"]):
        g = g.sort_values("stop_sequence")
        lat = [g["depot_lat"].iat[0], *g["lat"], g["depot_lat"].iat[0]]
        lon = [g["depot_lon"].iat[0], *g["lon"], g["depot_lon"].iat[0]]
        fig.add_trace(go.Scattermap(lat=lat, lon=lon, mode="lines+markers", name=vid, line=dict(width=3, color=colors[wid]),
                                    marker=dict(size=7, color=colors[wid]),
                                    text=[f"{wid} depot"] + [f"{vid} stop {q}: {z} ({p} pkg)" for q, z, p in
                                                             zip(g["stop_sequence"], g["stop_id"], g["packages"])] + [f"{wid} depot"],
                                    hoverinfo="text"))
    d = s.drop_duplicates("warehouse_id")
    fig.add_trace(go.Scattermap(lat=d["depot_lat"], lon=d["depot_lon"], mode="markers+text", name="depot",
                                marker=dict(size=20, color="#0b0b0b"), text=d["warehouse_id"], textposition="top right"))
    center, zoom = VIEW[net]
    fig.update_layout(map=dict(style="open-street-map", center=center, zoom=zoom), height=height, margin=dict(l=0, r=0, t=0, b=0),
                      showlegend=False)
    return fig


def page_routing():
    st.title("Delivery route optimisation (CVRP)")
    badge("simulated")
    if not need("optimized_delivery_routes.csv", "vehicle_assignments.csv", "route_comparison.csv"):
        return
    st.latex(r"\min\sum_k\sum_i\sum_j d_{ij}x_{ijk}\quad\text{s.t. each stop visited once, routes start/end at depot, "
             r"load}\le Q_v,\ \text{route length}\le L_{max}")
    st.caption("Weekly consolidated delivery plan; one package = one forecast order; distances are approximate road km "
               "(great-circle × 1.2). Routes are drawn as straight segments between stops.")
    net = st.radio("Network", ["CONUS", "Puerto Rico"], horizontal=True)
    stops, va, comp = load("optimized_delivery_routes.csv"), load("vehicle_assignments.csv"), load("route_comparison.csv")
    v = va[va["network"] == net]
    k = st.columns(5)
    k[0].metric("Vehicles", v["vehicle_id"].nunique())
    k[1].metric("Total distance / wk", f"{v['distance_km'].sum():,.0f} km")
    k[2].metric("Estimated driving + service time", f"{v['duration_h'].sum():,.1f} h")
    k[3].metric("Mean vehicle utilisation", f"{v['utilization_pct'].mean():.1f}%")
    k[4].metric("Routing cost / wk", f"${v['route_cost'].sum():,.0f}")
    depots = st.multiselect("Depots", sorted(v["warehouse_id"].unique()), default=sorted(v["warehouse_id"].unique()))
    st.plotly_chart(_route_map(stops, net, depots), use_container_width=True)
    st.subheader("Vehicle assignments (Guided Local Search)")
    st.dataframe(v[v["warehouse_id"].isin(depots)][["vehicle_id", "warehouse_id", "n_stops", "packages", "vehicle_capacity",
                                                    "utilization_pct", "distance_km", "duration_h", "route_cost", "route_sequence"]].round(2),
                 hide_index=True, use_container_width=True)
    st.subheader("Algorithm comparison")
    cc = comp[comp["network"] == net].copy()
    cc["method"] = cc["method"].map(METHOD_LABEL)
    st.dataframe(cc[["method", "vehicles", "total_distance_km", "total_duration_h", "fleet_utilization_pct", "capacity_violations",
                     "route_length_violations", "unserved_stops", "all_feasible", "runtime_s"]].round(2), hide_index=True,
                 use_container_width=True)


def page_performance():
    st.title("Algorithm performance")
    badge("simulated")
    if not need("experiment_warehouse_comparison.csv", "experiment_routing_comparison.csv"):
        return
    wc, rc = load("experiment_warehouse_comparison.csv"), load("experiment_routing_comparison.csv")
    st.subheader("Warehouse location: Random vs K-Means vs CFLP vs GA")
    c1, c2 = st.columns(2)
    fig = px.bar(wc, x="method", y="total_cost", color="network", barmode="group", color_discrete_map=NET_COLORS,
                 text=wc["total_cost"].round(0), title="Total cost per week (USD)")
    c1.plotly_chart(layout_fig(fig, 420), use_container_width=True)
    fig = px.bar(wc, x="method", y="runtime_s", color="network", barmode="group", color_discrete_map=NET_COLORS,
                 log_y=True, title="Runtime (s, log scale)")
    c2.plotly_chart(layout_fig(fig, 420), use_container_width=True)
    cols = ["network", "method", "total_cost", "gap_vs_cflp_pct", "avg_distance_km_order_weighted", "mean_utilization",
            "unserved_units", "feasible", "runtime_s"] + [c for c in wc.columns if c.startswith("cost_reduction")]
    st.dataframe(wc[cols].round(2), hide_index=True, use_container_width=True)
    st.subheader("Routing: Nearest Neighbor vs standard OR-Tools vs Guided Local Search")
    rc2 = rc.copy(); rc2["method"] = rc2["method"].map(METHOD_LABEL)
    c1, c2 = st.columns(2)
    fig = px.bar(rc2, x="method", y="total_distance_km", color="network", barmode="group", color_discrete_map=NET_COLORS,
                 text=rc2["total_distance_km"].round(0), title="Total route km per week")
    c1.plotly_chart(layout_fig(fig, 420), use_container_width=True)
    fig = px.bar(rc2, x="method", y="vehicles", color="network", barmode="group", color_discrete_map=NET_COLORS,
                 title="Vehicles used")
    c2.plotly_chart(layout_fig(fig, 420), use_container_width=True)
    cols = ["network", "method", "total_distance_km", "total_duration_h", "vehicles", "fleet_utilization_pct",
            "capacity_violations", "route_length_violations", "all_feasible", "runtime_s"] + [c for c in rc.columns if "reduction" in c]
    st.dataframe(rc2[cols].round(2), hide_index=True, use_container_width=True)
    fi = load("forecast_impact_comparison.csv")
    if fi is not None:
        st.subheader("Forecasting impact on warehouse planning (13 held-out weeks)")
        st.dataframe(fi[["network", "scenario", "warehouses_opened", "realised_total_cost", "realised_unserved_units",
                         "capacity_violation_units_if_plan_kept", "regret_vs_oracle_pct", "plan_proven_optimal"]].round(2),
                     hide_index=True, use_container_width=True)
    sens = load("sensitivity_analysis.csv")
    if sens is not None:
        st.subheader("Sensitivity analysis")
        s = sens[sens["experiment"] == "warehouse"]
        p = st.selectbox("Parameter", s["parameter"].unique())
        g = s[s["parameter"] == p]
        fig = px.line(g, x="value", y="total_cost", color="network", markers=True, color_discrete_map=NET_COLORS,
                      text="n_open", title=f"Total cost vs {p} (labels = warehouses opened)")
        fig.update_traces(textposition="top center")
        st.plotly_chart(layout_fig(fig, 380), use_container_width=True)
    rb = load("robustness_analysis.csv")
    if rb is not None:
        st.subheader("Robustness to demand changes")
        st.dataframe(rb.round(2), hide_index=True, use_container_width=True)


@st.cache_data(show_spinner=False, max_entries=32)
def run_what_if(net: str, p_mode: str, n_wh: int, capacity: float, fixed: float, cost_km: float, growth: float,
                veh_cap: int, n_veh: int, time_limit: float):
    """Actual re-optimisation: CFLP (CBC) -> allocation -> CVRP (standard + GLS). Cached per parameter set."""
    from src.customer_allocation import allocation_table, warehouse_table
    from src.vehicle_routing import build_depot_instances, solve_network_routing, summarize_routing
    from src.warehouse_cflp import build_problem, evaluate_configuration, solve_cflp

    ov = {"capacity_units_per_week": capacity, "fixed_cost_per_week": fixed, "cost_per_order_km": cost_km,
          "demand_growth": growth / 100}
    if p_mode == "fixed":
        ov.update(min_warehouses=n_wh, max_warehouses=n_wh)
    prob = build_problem(net, overrides=ov)
    sol = solve_cflp(prob, allow_unserved=True, time_limit_s=60)
    ev = evaluate_configuration(prob, sol.open, sol.assign, sol.unserved_fraction)
    al, wh = allocation_table(prob, sol.assign, "what-if"), warehouse_table(prob, sol.open, sol.assign, "what-if")
    inst = build_depot_instances(al, wh, net, {"vehicle_capacity_packages": veh_cap, "vehicles_per_depot": n_veh})
    R, S, F, T = solve_network_routing(inst, methods=("ortools_standard", "ortools_gls"), time_limit_s=time_limit)
    comp = summarize_routing(R, F, T) if len(R) else pd.DataFrame()
    return ev, al, wh, S, comp, sol.termination, sol.gap, prob.candidates


def page_what_if():
    st.title("What-if simulation")
    st.write("Change the assumptions and press **Run optimization**. The CFLP is re-solved with CBC, zones are re-allocated, "
             "and the vehicle routes are re-optimised with OR-Tools (standard search and Guided Local Search). Nothing on "
             "this page is pre-computed.")
    cfg = load_config()
    net = st.radio("Network", ["CONUS", "Puerto Rico"], horizontal=True)
    oc, rc = cfg["optimization"]["networks"][net], cfg["routing"]["networks"][net]
    with st.form("whatif"):
        c1, c2, c3 = st.columns(3)
        p_mode = c1.radio("Number of warehouses", ["optimise", "fixed"], horizontal=True)
        n_wh = c1.slider("Fixed number of warehouses", 1, int(oc["max_warehouses"]), min(4, int(oc["max_warehouses"])))
        capacity = c1.number_input("Warehouse capacity (units/week)", 10.0, 2000.0, float(oc["capacity_units_per_week"]), 5.0)
        fixed = c2.number_input("Warehouse opening cost (USD/week)", 0.0, 50000.0, float(oc["fixed_cost_per_week"]), 100.0)
        cost_km = c2.number_input("Transport cost (USD per order-km)", 0.0, 5.0, float(oc["cost_per_order_km"]), 0.01)
        growth = c2.slider("Demand growth (%)", -50, 100, 0, 5)
        veh_cap = c3.number_input("Vehicle capacity (packages)", 1, 500, int(rc["vehicle_capacity_packages"]), 1)
        n_veh = c3.number_input("Vehicles per depot", 1, 50, int(rc["vehicles_per_depot"]), 1)
        tl = c3.slider("GLS time per depot (s)", 1, 10, 2)
        go_btn = st.form_submit_button("Run optimization", type="primary")
    if not go_btn:
        st.info("Set parameters and press Run optimization.")
        return
    total_units = load("cflp_zone_demand_forecast.csv").query("network == @net")["forecast_per_period_units"].sum() * (1 + growth / 100)
    max_open = n_wh if p_mode == "fixed" else oc["max_warehouses"]
    if capacity * max_open < total_units:
        st.warning(f"Capacity check: {max_open} × {capacity:.0f} = {capacity * max_open:.0f} units/week < demand "
                   f"{total_units:.1f}. The solver will report unserved demand.")
    with st.spinner("Solving CFLP and routing..."):
        ev, al, wh, S, comp, term, gap, cands = run_what_if(net, p_mode, n_wh, capacity, fixed, cost_km, float(growth),
                                                             int(veh_cap), int(n_veh), float(tl))
    feasible_routes = bool(len(comp) and comp["all_feasible"].all())
    if ev["feasible"] and feasible_routes:
        st.success(f"Feasible configuration (CFLP termination: {term}).")
    else:
        st.error(f"Infeasible configuration: unserved units {ev['unserved_units']:.1f}, "
                 f"routing feasible: {feasible_routes} (CFLP termination: {term}).")
    base = load("warehouse_algorithm_comparison.csv")
    b = base[(base["network"] == net) & base["method"].str.startswith("CFLP")].iloc[0]
    k = st.columns(6)
    k[0].metric("Warehouses", ev["n_open"], ev["n_open"] - int(b["n_open"]))
    k[1].metric("Opening cost / wk", f"${ev['opening_cost']:,.0f}", f"{ev['opening_cost'] - b['opening_cost']:,.0f}", delta_color="inverse")
    k[2].metric("Transport cost / wk", f"${ev['transport_cost']:,.0f}", f"{ev['transport_cost'] - b['transport_cost']:,.0f}", delta_color="inverse")
    k[3].metric("Total cost / wk", f"${ev['total_cost']:,.0f}", f"{ev['total_cost'] - b['total_cost']:,.0f}", delta_color="inverse")
    k[4].metric("Max utilisation", f"{100 * ev['max_utilization']:.1f}%")
    k[5].metric("Unserved units", f"{ev['unserved_units']:.1f}")
    st.caption("Deltas compare with the baseline CFLP solution from config.yaml.")
    c1, c2 = st.columns(2)
    c1.markdown("**Warehouses and allocation**")
    c1.plotly_chart(_warehouse_map(al, wh, cands, net, False, 480), use_container_width=True)
    c2.markdown("**Guided Local Search routes**")
    if len(S):
        c2.plotly_chart(_route_map(S[S["method"] == "ortools_gls"], net, None, 480), use_container_width=True)
    if len(comp):
        comp = comp.copy(); comp["method"] = comp["method"].map(METHOD_LABEL)
        st.dataframe(comp[["method", "vehicles", "total_distance_km", "total_duration_h", "fleet_utilization_pct",
                           "capacity_violations", "route_length_violations", "unserved_stops", "all_feasible", "runtime_s"]].round(2),
                     hide_index=True, use_container_width=True)
    st.dataframe(wh[wh["is_open"]][["warehouse_id", "dominant_city", "assigned_zones", "assigned_units_per_week",
                                    "capacity_units_per_week", "utilization_pct"]].round(2), hide_index=True, use_container_width=True)


def page_reports():
    st.title("Reports and downloads")
    files = [("Forecast results (CFLP demand input)", "cflp_zone_demand_forecast.csv"),
             ("Forecast evaluation", "forecast_evaluation.csv"), ("Selected forecast models", "selected_forecast_model.csv"),
             ("Warehouse locations", "optimal_warehouse_locations.csv"), ("Customer allocation", "selected_allocation.csv"),
             ("Warehouse utilisation", "warehouse_capacity_report.csv"), ("Vehicle assignments", "vehicle_assignments.csv"),
             ("Optimised routes (stops)", "optimized_delivery_routes.csv"),
             ("Warehouse algorithm comparison", "experiment_warehouse_comparison.csv"),
             ("Routing algorithm comparison", "experiment_routing_comparison.csv"),
             ("Forecast impact", "forecast_impact_comparison.csv"), ("Sensitivity results", "sensitivity_analysis.csv"),
             ("Robustness results", "robustness_analysis.csv"), ("Final performance summary", "final_performance_summary.csv")]
    for label, f in files:
        p = OUT / f
        c1, c2 = st.columns([3, 1])
        c1.write(f"**{label}**: `{f}`" + ("" if p.exists() else " (not generated yet)"))
        if p.exists():
            c2.download_button("Download", p.read_bytes(), file_name=f, mime="text/csv", key=f)
    rp = ROOT / "reports" / "final_project_report.md"
    if rp.exists():
        st.download_button("Download final project report (Markdown)", rp.read_bytes(), "final_project_report.md")


PAGES = {"Executive overview": page_overview, "Data analytics": page_analytics, "Demand forecasting": page_forecast,
         "Warehouse optimisation": page_warehouse, "Delivery routing": page_routing,
         "Algorithm performance": page_performance, "What-if simulation": page_what_if, "Reports & downloads": page_reports}

with st.sidebar:
    st.markdown("### 📦 Logistics optimiser")
    page = st.radio("Page", list(PAGES), label_visibility="collapsed")
    st.markdown("---")
    st.caption("Data: DataCo Smart Supply Chain (Kaggle). Costs, capacities and fleet are documented simulation "
               "assumptions (config.yaml). Distances are approximate road km.")
PAGES[page]()
