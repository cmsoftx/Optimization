"""Static (matplotlib) and interactive (folium) figures.

Colour roles (validated categorical palette, first three slots, so every
pair passes colour-vision-deficiency separation):
    CONUS = blue, Puerto Rico = orange, Hawaii = aqua.
Regimes: pre-break = blue, post-break = orange.
Maps use plain lon/lat axes with an equal-distance aspect correction. No
basemap tiles are downloaded for the static figures.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import get_path  # noqa: E402

NET_COLORS = {"CONUS": "#2a78d6", "Puerto Rico": "#eb6834", "Hawaii": "#1baf7a"}
REG_COLORS = {"pre_2017_10": "#2a78d6", "post_2017_10": "#eb6834"}
REG_LABELS = {"pre_2017_10": "Before 2017-10", "post_2017_10": "From 2017-10"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
NETWORKS = ["CONUS", "Puerto Rico", "Hawaii"]

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 11,
    "font.size": 9, "legend.frameon": False, "lines.linewidth": 2,
})


def _save(fig, name: str) -> Path:
    path = get_path("figures_dir") / name
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _geo_aspect(ax, lat_mean: float) -> None:
    ax.set_aspect(1.0 / np.cos(np.radians(lat_mean)))


def _bubble(units: pd.Series, max_size: float = 900) -> np.ndarray:
    return max_size * np.sqrt(units / units.max()) + 4


def plot_zone_map(zones: pd.DataFrame, network: str, ax, label_top: int = 8, max_size: float = 900,
                  label_by: str = "city"):
    z = zones[zones["network"] == network]
    ax.scatter(z["centroid_lon"], z["centroid_lat"], s=_bubble(z["units"], max_size),
               color=NET_COLORS[network], alpha=0.55, edgecolor="#fcfcfb", linewidth=0.8)
    # Label the largest zones, skipping any that would sit on top of an existing label.
    span = max(z["centroid_lon"].max() - z["centroid_lon"].min(), z["centroid_lat"].max() - z["centroid_lat"].min())
    min_sep = 0.06 * span
    placed: list[tuple[float, float]] = []
    for r in z.sort_values("units", ascending=False).itertuples():
        if len(placed) >= label_top:
            break
        if any(np.hypot(r.centroid_lon - x, r.centroid_lat - y) < min_sep for x, y in placed):
            continue
        name = r.zone_id if label_by == "zone" else r.dominant_city
        ax.annotate(f"{name}\n{r.units:,.0f} u", (r.centroid_lon, r.centroid_lat), fontsize=7,
                    color=INK, xytext=(5, 5), textcoords="offset points")
        placed.append((r.centroid_lon, r.centroid_lat))
    pad_x = 0.08 * (z["centroid_lon"].max() - z["centroid_lon"].min() + 1e-3)
    pad_y = 0.15 * (z["centroid_lat"].max() - z["centroid_lat"].min() + 1e-3)
    ax.set_xlim(z["centroid_lon"].min() - pad_x, z["centroid_lon"].max() + pad_x)
    ax.set_ylim(z["centroid_lat"].min() - pad_y, z["centroid_lat"].max() + pad_y)
    _geo_aspect(ax, z["centroid_lat"].mean())
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    return ax


def fig_zone_maps(zones: pd.DataFrame) -> list[Path]:
    paths = []
    fig, ax = plt.subplots(figsize=(12, 6.5))
    plot_zone_map(zones, "CONUS", ax, label_top=10)
    z = zones[zones["network"] == "CONUS"]
    ax.set_title(f"CONUS demand zones: {len(z)} zones (diameter ≤ 50 km); bubble area ∝ units, Jan 2015–Jan 2018")
    paths.append(_save(fig, "phase2_demand_zones_conus.png"))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    for ax, net, by in zip(axes, ["Puerto Rico", "Hawaii"], ["zone", "city"]):
        plot_zone_map(zones, net, ax, label_top=5, max_size=1200, label_by=by)
        n = (zones["network"] == net).sum()
        ax.set_title(f"{net}: {n} zones (≤ 10 km)\nbubble area ∝ units", fontsize=10)
    axes[0].text(0.01, 0.02, "All PR zones carry Customer City 'Caguas' (a catch-all label), so zone IDs are shown",
                 transform=axes[0].transAxes, fontsize=7, color=MUTED)
    paths.append(_save(fig, "phase2_demand_zones_pr_hi.png"))
    return paths


def fig_monthly(monthly: pd.DataFrame, break_month: str = "2017-10") -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True)
    months = sorted(monthly["month"].unique())
    x = {m: i for i, m in enumerate(months)}
    for ax, col, title in [(axes[0], "orders", "Orders (deliveries) per month"),
                           (axes[1], "units", "Units per month (Order Item Quantity)")]:
        for net in NETWORKS:
            g = monthly[monthly["network"] == net]
            ax.plot(g["month"].map(x), g[col], color=NET_COLORS[net], label=net, marker="o", markersize=3)
        ax.axvline(x[break_month] - 0.5, color=MUTED, ls="--", lw=1)
        ax.text(x[break_month] - 0.4, ax.get_ylim()[1] * 0.92, "regime change", color=MUTED, fontsize=8)
        ax.set_title(title); ax.set_ylabel(col)
    axes[0].legend(ncol=3, loc="lower left")
    axes[1].set_xticks(range(len(months)), months, rotation=90)
    fig.suptitle("Monthly demand by network: orders rise from 2017-10 while units collapse", fontweight="bold")
    return _save(fig, "phase2_monthly_demand.png")


def fig_weekly(weekly: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(12, 4))
    w = weekly[~weekly["partial_week"]]
    for net in ["CONUS", "Puerto Rico"]:
        g = w[w["network"] == net].sort_values("week_start")
        ax.plot(g["week_start"], g["orders"], color=NET_COLORS[net], lw=1, alpha=0.45)
        ax.plot(g["week_start"], g["orders"].rolling(4, center=True).mean(), color=NET_COLORS[net],
                label=f"{net} (4-week rolling mean)")
    ax.axvline(pd.Timestamp("2017-10-01"), color=MUTED, ls="--", lw=1)
    ax.set_title("Weekly orders (complete weeks only): no visible seasonality, step up from 2017-10")
    ax.set_ylabel("orders / week"); ax.legend()
    return _save(fig, "phase2_weekly_orders.png")


def fig_day_of_week(dow: pd.DataFrame) -> Path:
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.6), sharey=True)
    for ax, net in zip(axes, ["CONUS", "Puerto Rico"]):
        g = dow[dow["network"] == net]
        for reg in ["pre_2017_10", "post_2017_10"]:
            gg = g[g["regime"] == reg].set_index("weekday").reindex(order)
            # dots, not bars: the y-axis does not start at zero
            ax.plot(np.arange(7), gg["index_vs_mean"], color=REG_COLORS[reg], marker="o", markersize=7,
                    lw=1.2, label=REG_LABELS[reg])
        ax.axhline(1, color=MUTED, lw=1)
        ax.set_xticks(range(7), [d[:3] for d in order]); ax.set_ylim(0.8, 1.2)
        ax.set_title(f"{net}: orders per weekday ÷ mean")
    axes[0].set_ylabel("index (1 = average day)"); axes[0].legend()
    fig.suptitle("No weekday pattern: every weekday is within a few % of the mean", fontweight="bold")
    return _save(fig, "phase2_day_of_week.png")


def fig_category_shift(category: pd.DataFrame, network: str = "CONUS", top: int = 12) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, reg in zip(axes, ["pre_2017_10", "post_2017_10"]):
        g = category[(category["network"] == network) & (category["regime"] == reg)].nlargest(top, "units")[::-1]
        ax.barh(g["category_name"], 100 * g["unit_share"], color=REG_COLORS[reg], height=0.7)
        for y, v in enumerate(100 * g["unit_share"]):
            ax.text(v + 0.2, y, f"{v:.1f}%", va="center", fontsize=7, color=MUTED)
        ax.set_title(f"{network} {REG_LABELS[reg]}: top {top} categories (% of units)")
        ax.set_xlabel("% of units")
    fig.suptitle("Product mix changes completely at the break (sporting goods → media/clothing)", fontweight="bold")
    return _save(fig, "phase2_category_shift.png")


def fig_regime(regime: pd.DataFrame) -> Path:
    metrics = [("orders_per_day", "Orders per day"), ("units_per_order", "Units per order"),
               ("items_per_order", "Items per order"), ("units_per_day", "Units per day")]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6))
    w = 0.38
    for ax, (col, title) in zip(axes, metrics):
        for k, reg in enumerate(["pre_2017_10", "post_2017_10"]):
            g = regime[regime["regime"] == reg].set_index("network").reindex(NETWORKS)
            ax.bar(np.arange(3) + (k - 0.5) * w, g[col], width=w - 0.03, color=REG_COLORS[reg], label=REG_LABELS[reg])
        ax.set_xticks(range(3), ["CONUS", "PR", "HI"]); ax.set_title(title)
    axes[0].legend()
    r = regime.set_index(["network", "regime"])
    ratio = r.loc[("CONUS", "pre_2017_10"), "units_per_order"] / r.loc[("CONUS", "post_2017_10"), "units_per_order"]
    fig.suptitle(f"Before vs from 2017-10: more orders, {ratio:.1f}x fewer units per order (CONUS)", fontweight="bold")
    return _save(fig, "phase2_regime_comparison.png")


def fig_concentration(conc: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for net in NETWORKS:
        g = conc[conc["network"] == net]
        ax.plot(np.r_[0, g["zone_share_cum"]] * 100, np.r_[0, g["units_share_cum"]] * 100,
                color=NET_COLORS[net], label=f"{net} ({len(g)} zones)")
    ax.plot([0, 100], [0, 100], color=MUTED, lw=1, ls=":", label="uniform")
    ax.axhline(80, color=GRID, lw=1)
    ax.set_xlabel("% of zones (largest first)"); ax.set_ylabel("% of units")
    ax.set_title("Demand concentration across zones"); ax.legend()
    return _save(fig, "phase2_zone_concentration.png")


def fig_spatial_stability(zone_daily: pd.DataFrame, network: str = "CONUS") -> Path:
    s = (zone_daily[zone_daily["network"] == network].groupby(["zone_id", "regime"])["orders"].sum()
         .unstack(fill_value=0))
    share = 100 * s / s.sum()
    rho = share["pre_2017_10"].rank().corr(share["post_2017_10"].rank())  # Spearman on all zones
    both = share[(share > 0).all(axis=1)]
    fig, ax = plt.subplots(figsize=(6, 5.4))
    ax.scatter(both["pre_2017_10"], both["post_2017_10"], s=14, color=NET_COLORS[network], alpha=0.6)
    lim = [both.values.min() / 1.5, both.values.max() * 1.5]
    ax.plot(lim, lim, color=MUTED, lw=1, ls=":", label="equal share")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("zone share of orders before 2017-10 (%)"); ax.set_ylabel("zone share of orders from 2017-10 (%)")
    ax.set_title(f"{network}: zone demand shares before vs after the break\n"
                 f"Spearman ρ = {rho:.2f} over all {len(share)} zones", fontsize=10)
    ax.text(0.02, 0.97, f"{len(share) - len(both)} zones with zero orders in one period not shown (log axes).\n"
            "Horizontal banding: post-break period is only 4 months.",
            transform=ax.transAxes, fontsize=7, color=MUTED, va="top")
    ax.legend(loc="lower right")
    return _save(fig, "phase2_zone_spatial_stability.png")


def fig_sparsity(sparsity: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    grans = ["day", "week", "month"]
    w = 0.27
    for k, net in enumerate(NETWORKS):
        g = sparsity[sparsity["network"] == net].set_index("granularity").reindex(grans)
        ax.bar(np.arange(3) + (k - 1) * w, 100 * g["zero_share"], width=w - 0.03, color=NET_COLORS[net], label=net)
    ax.set_xticks(range(3), [f"zone-{g}" for g in grans]); ax.set_ylabel("% of periods with zero orders")
    ax.set_title("Demand sparsity by time granularity (drives forecast granularity)"); ax.legend()
    return _save(fig, "phase2_demand_sparsity.png")


def folium_zone_map(zones: pd.DataFrame, path: Path | None = None) -> Path:
    """Interactive map of demand zones (tiles are fetched by the viewer's browser)."""
    import folium

    path = path or get_path("figures_dir") / "phase2_demand_zones_map.html"
    m = folium.Map(location=[37.5, -90], zoom_start=4, tiles="OpenStreetMap")
    for net in NETWORKS:
        fg = folium.FeatureGroup(name=f"{net} zones", show=True)
        z = zones[zones["network"] == net]
        umax = z["units"].max()
        for r in z.itertuples():
            folium.CircleMarker(
                location=[r.centroid_lat, r.centroid_lon], radius=float(3 + 22 * np.sqrt(r.units / umax)),
                color=NET_COLORS[net], weight=1, fill=True, fill_opacity=0.5,
                tooltip=(f"<b>{r.zone_id}</b> ({r.dominant_city}, {r.dominant_state})<br>"
                         f"units {r.units:,} · orders {r.n_orders:,} · customers {r.n_customers:,}<br>"
                         f"share of {net} units {100 * r.share_of_network_units:.2f}%<br>"
                         f"max radius {r.max_km_from_centroid:.1f} km"),
            ).add_to(fg)
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(path))
    return path


def make_phase2_figures(zones, zone_daily, tables: dict) -> list[Path]:
    paths = fig_zone_maps(zones)
    paths += [fig_monthly(tables["monthly"]), fig_weekly(tables["weekly"]), fig_day_of_week(tables["dow"]),
              fig_category_shift(tables["category"]), fig_regime(tables["regime"]),
              fig_concentration(tables["concentration"]), fig_spatial_stability(zone_daily),
              fig_sparsity(tables["sparsity"]), folium_zone_map(zones)]
    return paths
