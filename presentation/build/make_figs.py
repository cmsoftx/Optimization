"""Deck graphics built only from the project's real output files (coordinates, allocations, routes, GA history)."""
import sys, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT = sys.argv[1]; OUT = sys.argv[2]
O = f"{ROOT}/data/outputs/"
IVORY, GRAPH, TEAL, CORAL, SAGE, GREY, CHAR = "#F7F4EE", "#22272B", "#0F7C74", "#D9653B", "#7FA37A", "#A8A29A", "#1F2427"
WH6 = [TEAL, CORAL, "#5B6770", "#C99A2E", "#7FA37A", "#8E5B7A"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": "#CFC8BC", "axes.labelcolor": GRAPH,
                     "xtick.color": "#5F5A53", "ytick.color": "#5F5A53", "text.color": GRAPH})

def geo(ax, lat): ax.set_aspect(1 / np.cos(np.radians(lat)))
def clean(ax):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)

al = pd.read_csv(O + "selected_allocation.csv"); wh = pd.read_csv(O + "selected_warehouses.csv")
st = pd.read_csv(O + "all_method_route_stops.csv"); zones = pd.read_csv(O + "demand_zones.csv")
cands = pd.read_csv(O + "candidate_warehouses.csv")

# 1. Title background: real CONUS GLS routes on charcoal
fig = plt.figure(figsize=(13.333, 7.5), dpi=200); fig.patch.set_facecolor(CHAR)
ax = fig.add_axes([0.52, 0.08, 0.46, 0.84]); ax.set_facecolor(CHAR)
z = zones[zones.network == "CONUS"]
ax.scatter(z.centroid_lon, z.centroid_lat, s=4 + 40 * np.sqrt(z.units / z.units.max()), color="#56606A", alpha=0.6, lw=0)
g = st[(st.network == "CONUS") & (st.method == "ortools_gls")]
for (w, v), r in g.groupby(["warehouse_id", "vehicle_id"]):
    r = r.sort_values("stop_sequence")
    ax.plot(np.r_[r.depot_lon.iat[0], r.lon, r.depot_lon.iat[0]], np.r_[r.depot_lat.iat[0], r.lat, r.depot_lat.iat[0]],
            color=TEAL, lw=1.1, alpha=0.9)
    ax.scatter(r.lon, r.lat, s=7, color="#9FD3C9", zorder=3, lw=0)
d = g.drop_duplicates("warehouse_id"); ax.scatter(d.depot_lon, d.depot_lat, s=150, color=CORAL, edgecolor=IVORY, lw=1.4, zorder=5, marker="s")
geo(ax, 38); clean(ax); fig.savefig(f"{OUT}/title_network.png", facecolor=CHAR); plt.close(fig)

# 2. Demand-zone maps (CONUS + PR + HI insets)
fig = plt.figure(figsize=(9.6, 5.4), dpi=220); fig.patch.set_facecolor(IVORY)
ax = fig.add_axes([0.02, 0.08, 0.72, 0.88]); ax.set_facecolor(IVORY)
ax.scatter(z.centroid_lon, z.centroid_lat, s=6 + 380 * np.sqrt(z.units / z.units.max()), color=TEAL, alpha=0.55, edgecolor="white", lw=0.5)
for r in z.nlargest(30, "units").drop_duplicates("dominant_state").head(7).itertuples():
    ax.annotate(r.dominant_city, (r.centroid_lon, r.centroid_lat), xytext=(5, 5), textcoords="offset points", fontsize=8.5)
geo(ax, 38); clean(ax); ax.set_title("Contiguous US: 312 zones (every pair ≤ 50 km apart)", fontsize=11, loc="left", color=GRAPH)
for k, (net, box, col, lab) in enumerate([("Puerto Rico", [0.76, 0.52, 0.23, 0.38], CORAL, "Puerto Rico: 25 zones (≤ 10 km)"),
                                          ("Hawaii", [0.76, 0.08, 0.23, 0.33], "#5B6770", "Hawaii: 6 zones (analysis only)")]):
    a = fig.add_axes(box); a.set_facecolor(IVORY); zz = zones[zones.network == net]
    a.scatter(zz.centroid_lon, zz.centroid_lat, s=10 + 500 * np.sqrt(zz.units / zz.units.max()), color=col, alpha=0.55, edgecolor="white", lw=0.5)
    a.margins(0.22); geo(a, zz.centroid_lat.mean()); clean(a); a.set_title(lab, fontsize=9, loc="left")
    for s in a.spines.values(): s.set_visible(True); s.set_color("#D8D1C4")
fig.text(0.01, 0.02, "Bubble area ∝ units ordered, Jan 2015 – Jan 2018. Points are zone centroids (unit-weighted) of customer coordinates.", fontsize=8, color="#6B655D")
fig.savefig(f"{OUT}/zones_map.png", facecolor=IVORY); plt.close(fig)

# 3. CONUS allocation map with selected warehouses
def alloc_map(net, fname, size, lat0, label_util=True):
    fig = plt.figure(figsize=size, dpi=220); fig.patch.set_facecolor(IVORY)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.98]); ax.set_facecolor(IVORY)
    a = al[al.network == net]; w = wh[(wh.network == net) & wh.is_open].reset_index(drop=True)
    col = {wid: WH6[i] for i, wid in enumerate(w.warehouse_id)}
    if net == "CONUS":
        c = cands[cands.network == net]; ax.scatter(c.centroid_lon, c.centroid_lat, s=26, facecolors="none", edgecolors=GREY, lw=0.9, zorder=2)
    for r in a.itertuples():
        ax.plot([r.zone_lon, r.warehouse_lon], [r.zone_lat, r.warehouse_lat], color=col[r.warehouse_id], lw=0.55, alpha=0.5)
    ax.scatter(a.zone_lon, a.zone_lat, s=6 + 120 * np.sqrt(a.forecast_orders_per_week / a.forecast_orders_per_week.max()),
               c=[col[x] for x in a.warehouse_id], alpha=0.8, edgecolor="white", lw=0.4, zorder=3)
    for k, r in w.iterrows():
        ax.scatter(r.centroid_lon, r.centroid_lat, marker="s", s=170, color=col[r.warehouse_id], edgecolor=GRAPH, lw=1.3, zorder=5)
        dy = (-24 if r.centroid_lat < w.centroid_lat.max() else 10) if net == "Puerto Rico" else 8
        east = net == "Puerto Rico" or r.centroid_lon > -80
        ax.annotate(f"{r.dominant_city}, {r.dominant_state}" + (f" ({r.warehouse_id[-2:]})  {r.utilization_pct:.1f}%" if net == "Puerto Rico" else f"  {r.utilization_pct:.1f}%"),
                    (r.centroid_lon, r.centroid_lat), xytext=(-11 if east else 9, dy if net == "Puerto Rico" else (-24 if east else 8)),
                    textcoords="offset points", fontsize=10, fontweight="bold",
                    ha="right" if east else "left",
                    color=GRAPH, bbox=dict(boxstyle="round,pad=0.25", fc=IVORY, ec="none", alpha=0.85), zorder=6)
    ax.margins(x=0.13, y=0.06); geo(ax, lat0); clean(ax); fig.savefig(f"{OUT}/{fname}", facecolor=IVORY); plt.close(fig)
alloc_map("CONUS", "alloc_conus.png", (9.0, 5.2), 38)
alloc_map("Puerto Rico", "alloc_pr.png", (5.0, 2.8), 18.2)

# 4. GA convergence (CONUS) with CFLP optimum
conv = pd.read_csv(O + "ga_convergence.csv"); comp = pd.read_csv(O + "warehouse_algorithm_comparison.csv")
opt = comp[(comp.network == "CONUS") & comp.method.str.startswith("CFLP")].cflp_objective_excl_handling.iat[0]
fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=220); fig.patch.set_facecolor(IVORY); ax.set_facecolor(IVORY)
for k, (seed, h) in enumerate(conv[conv.network == "CONUS"].groupby("seed")):
    ax.plot(h.generation, h.best_so_far, lw=1.8, color=[TEAL, CORAL, "#5B6770", "#C99A2E", SAGE][k], label=f"seed {seed}")
ax.axhline(opt, color=GRAPH, ls="--", lw=1.3); ax.text(81, opt, " CFLP optimum\n $18,348", va="center", fontsize=9)
ax.set_xlabel("generation"); ax.set_ylabel("best fitness so far (USD/week,\nopening + transport)")
ax.set_ylim(opt * 0.99, opt * 1.25); ax.set_xlim(0, 95); ax.grid(color="#E6E0D6", lw=0.6)
for s in ["top", "right"]: ax.spines[s].set_visible(False)
ax.legend(fontsize=8, frameon=False, ncol=1, loc="upper right", bbox_to_anchor=(0.86, 1)); fig.tight_layout()
fig.savefig(f"{OUT}/ga_convergence_conus.png", facecolor=IVORY); plt.close(fig)

# 5. Nearest Neighbor vs GLS for the Dallas depot (real routes)
dep = "WH-US-14"; rr = pd.read_csv(O + "all_method_routes.csv")
fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.6), dpi=220); fig.patch.set_facecolor(IVORY)
for ax, m, ttl in zip(axes, ["nearest_neighbor", "ortools_gls"], ["Nearest Neighbor (greedy construction)", "OR-Tools Guided Local Search"]):
    ax.set_facecolor(IVORY); g = st[(st.warehouse_id == dep) & (st.method == m)]
    info = rr[(rr.warehouse_id == dep) & (rr.method == m)]
    for k, (v, r) in enumerate(g.groupby("vehicle_id")):
        r = r.sort_values("stop_sequence"); km = info[info.vehicle_id == v].distance_km.iat[0]
        bad = km > 3000
        ax.plot(np.r_[r.depot_lon.iat[0], r.lon, r.depot_lon.iat[0]], np.r_[r.depot_lat.iat[0], r.lat, r.depot_lat.iat[0]],
                color=CORAL if bad else [TEAL, "#5B6770", SAGE, "#C99A2E", "#8E5B7A"][k % 5], lw=1.8 if bad else 1.4,
                ls="-" if not bad else (0, (5, 2)), label=f"{v[-3:]}: {km:,.0f} km" + ("  > 3,000 km limit" if bad else ""))
        ax.scatter(r.lon, r.lat, s=14, color=GRAPH, zorder=3, lw=0)
    ax.scatter(g.depot_lon.iat[0], g.depot_lat.iat[0], marker="s", s=150, color=GRAPH, zorder=5)
    tot = info.distance_km.sum()
    ax.set_title(f"{ttl}\n{len(info)} vehicles · {tot:,.0f} km", fontsize=11, loc="left")
    ax.margins(0.05); geo(ax, 32); clean(ax); ax.legend(fontsize=8, frameon=False, loc="upper right", bbox_to_anchor=(1.02, 1.0))
fig.tight_layout(); fig.savefig(f"{OUT}/nn_vs_gls_dallas.png", facecolor=IVORY); plt.close(fig)

# 6. CONUS GLS routes (all depots) for the results slide
fig = plt.figure(figsize=(9.0, 5.0), dpi=220); fig.patch.set_facecolor(IVORY)
ax = fig.add_axes([0.01, 0.01, 0.98, 0.98]); ax.set_facecolor(IVORY)
g = st[(st.network == "CONUS") & (st.method == "ortools_gls")]
ids = list(wh[(wh.network == "CONUS") & wh.is_open].warehouse_id); col = {w: WH6[i] for i, w in enumerate(ids)}
for (w, v), r in g.groupby(["warehouse_id", "vehicle_id"]):
    r = r.sort_values("stop_sequence"); k = int(v[-2:])
    ax.plot(np.r_[r.depot_lon.iat[0], r.lon, r.depot_lon.iat[0]], np.r_[r.depot_lat.iat[0], r.lat, r.depot_lat.iat[0]],
            color=col[w], lw=1.4, ls=["-", (0, (4, 2)), (0, (1, 1.5)), "-."][(k - 1) % 4], alpha=0.95)
    ax.scatter(r.lon, r.lat, s=5 + 4 * r.packages, color=col[w], edgecolor="white", lw=0.4, zorder=3)
for w, r in g.groupby("warehouse_id"):
    ax.scatter(r.depot_lon.iat[0], r.depot_lat.iat[0], marker="s", s=160, color=col[w], edgecolor=GRAPH, lw=1.3, zorder=5)
    east = r.depot_lon.iat[0] > -80
    ax.annotate(f"{w} · {r.vehicle_id.nunique()} veh", (r.depot_lon.iat[0], r.depot_lat.iat[0]), xytext=(-10 if east else 8, -20 if east else 7),
                textcoords="offset points", ha="right" if east else "left",
                fontsize=9, fontweight="bold", bbox=dict(boxstyle="round,pad=0.2", fc=IVORY, ec="none", alpha=0.85))
ax.margins(x=0.06, y=0.06); geo(ax, 37); clean(ax); fig.savefig(f"{OUT}/gls_routes_conus.png", facecolor=IVORY); plt.close(fig)

# 7. Small depot-and-stops diagram data (real Livermore depot, GLS) for the CVRP model slide
g = st[(st.warehouse_id == "WH-US-37") & (st.method == "ortools_gls")]
fig, ax = plt.subplots(figsize=(4.6, 4.4), dpi=220); fig.patch.set_facecolor(IVORY); ax.set_facecolor(IVORY)
for k, (v, r) in enumerate(g.groupby("vehicle_id")):
    r = r.sort_values("stop_sequence")
    ax.plot(np.r_[r.depot_lon.iat[0], r.lon, r.depot_lon.iat[0]], np.r_[r.depot_lat.iat[0], r.lat, r.depot_lat.iat[0]],
            color=[TEAL, CORAL][k % 2], lw=1.8, label=f"vehicle {k + 1}: {int(r.packages.sum())} packages")
    ax.scatter(r.lon, r.lat, s=18 + 10 * r.packages, color=[TEAL, CORAL][k % 2], edgecolor="white", lw=0.6, zorder=3)
ax.scatter(g.depot_lon.iat[0], g.depot_lat.iat[0], marker="s", s=170, color=GRAPH, zorder=5)
ax.annotate("depot (Hialeah, FL)", (g.depot_lon.iat[0], g.depot_lat.iat[0]), xytext=(8, -14), textcoords="offset points", fontsize=9)
geo(ax, 28); clean(ax); fig.tight_layout()
fig.savefig(f"{OUT}/depot_example.png", facecolor=IVORY); plt.close(fig)
print("figures written")
