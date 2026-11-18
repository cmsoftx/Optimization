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


# Phase 3: forecasting figures
MODEL_COLORS = {"historical_average": "#2a78d6", "moving_average": "#eb6834", "random_forest": "#1baf7a",
                "xgboost": "#eda100", "share_x_recent_level": "#e87ba4", "post_break_average": "#6250d6",
                "oracle_window_mean": "#52514e"}
MODEL_LABELS = {"historical_average": "Historical avg", "moving_average": "Moving avg",
                "random_forest": "Random Forest", "xgboost": "XGBoost", "share_x_recent_level": "Share × recent level",
                "post_break_average": "Post-break average", "oracle_window_mean": "Oracle (noise floor)"}
FC_NETS = ["CONUS", "Puerto Rico"]


def fig_fc_network_series(pred: pd.DataFrame, gran: str = "W") -> Path:
    """Network-total actual vs one-step forecasts across validation, pre-break test and post-break test."""
    p = pred[(pred["granularity"] == gran) & (pred["mode"] == "one_step")
             & pred["eval_set"].isin(["pre_break_validation", "pre_break_test", "post_break_test"])]
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), sharex=True)
    for i, tgt in enumerate(["orders", "units"]):
        for j, net in enumerate(FC_NETS):
            ax = axes[i, j]
            g = p[(p["target"] == tgt) & (p["network"] == net)]
            s = g.groupby(["model", "period_start"])[["actual", "predicted"]].sum().reset_index()
            act = s[s["model"] == "historical_average"].set_index("period_start")["actual"]
            ax.plot(act.index, act.values, color=INK, lw=2.2, label="Actual")
            for m in ALL_FC_MODELS:
                mm = s[s["model"] == m]
                ax.plot(mm["period_start"], mm["predicted"], color=MODEL_COLORS[m], lw=1.4, label=MODEL_LABELS[m])
            for d, lab in [("2017-06-01", "pre-break test"), ("2017-10-01", "post-break test")]:
                ax.axvline(pd.Timestamp(d), color=MUTED, ls="--", lw=1)
                ax.text(pd.Timestamp(d), ax.get_ylim()[1] * 0.97, f" {lab}", color=MUTED, fontsize=7, va="top")
            ax.set_title(f"{net}: weekly {tgt} (network total), one-step-ahead")
            ax.set_ylabel(f"{tgt} / week")
    axes[0, 0].legend(ncol=5, fontsize=7, loc="lower left")
    for ax in axes[1]:
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("Actual vs predicted demand (sum over zones). Models trained only on data before each window",
                 fontweight="bold")
    return _save(fig, "phase3_actual_vs_predicted_network.png")


ALL_FC_MODELS = ["historical_average", "moving_average", "random_forest", "xgboost"]


def fig_fc_wape(evaluation: pd.DataFrame, gran: str = "W") -> Path:
    e = evaluation[(evaluation["granularity"] == gran) & (evaluation["tier"] == "all")
                   & (evaluation["level"] == "zone_period") & evaluation["network"].isin(FC_NETS)]
    combos = [("pre_break_test", "one_step", "none", "Pre-break\none-step"),
              ("pre_break_test", "horizon", "none", "Pre-break\n17-wk horizon"),
              ("post_break_test", "one_step", "none", "Post-break\none-step"),
              ("post_break_test", "horizon", "none", "Post-break\n17-wk horizon"),
              ("post_break_adapted", "horizon", "none", "Post adapted\nraw"),
              ("post_break_adapted", "horizon", "recalibrated", "Post adapted\nrecalibrated")]
    fig, axes = plt.subplots(2, 2, figsize=(14, 7.5), sharey="row")
    w = 0.2
    for i, tgt in enumerate(["orders", "units"]):
        for j, net in enumerate(FC_NETS):
            ax = axes[i, j]
            for k, m in enumerate(ALL_FC_MODELS):
                vals = []
                for es, mode, hd, _ in combos:
                    v = e[(e["eval_set"] == es) & (e["mode"] == mode) & (e["handling"] == hd) & (e["target"] == tgt)
                          & (e["network"] == net) & (e["model"] == m)]["WAPE"]
                    vals.append(float(v.iloc[0]) if len(v) else np.nan)
                ax.bar(np.arange(len(combos)) + (k - 1.5) * w, 100 * np.array(vals), width=w - 0.02,
                       color=MODEL_COLORS[m], label=MODEL_LABELS[m])
            ax.set_xticks(range(len(combos)), [c[3] for c in combos], fontsize=7)
            ax.set_title(f"{net}: {tgt}, zone-{'week' if gran == 'W' else 'month'} WAPE (%)")
            ax.set_ylabel("WAPE %")
    axes[0, 0].legend(ncol=4, fontsize=8)
    fig.suptitle("Forecast error by model, evaluation window and regime handling (lower is better)",
                 fontweight="bold")
    return _save(fig, f"phase3_model_wape_comparison_{gran}.png")


def fig_fc_tiers(evaluation: pd.DataFrame, eval_set: str = "pre_break_test", gran: str = "W") -> Path:
    e = evaluation[(evaluation["granularity"] == gran) & (evaluation["eval_set"] == eval_set)
                   & (evaluation["mode"] == "one_step") & (evaluation["level"] == "zone_period")
                   & evaluation["network"].isin(FC_NETS) & evaluation["tier"].isin(["high", "medium", "low"])]
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.5), sharey="row")
    tiers = ["high", "medium", "low"]
    w = 0.2
    for i, tgt in enumerate(["orders", "units"]):
        for j, net in enumerate(FC_NETS):
            ax = axes[i, j]
            for k, m in enumerate(ALL_FC_MODELS):
                g = e[(e["target"] == tgt) & (e["network"] == net) & (e["model"] == m)].set_index("tier").reindex(tiers)
                ax.bar(np.arange(3) + (k - 1.5) * w, 100 * g["WAPE"], width=w - 0.02, color=MODEL_COLORS[m],
                       label=MODEL_LABELS[m])
            ax.set_xticks(range(3), ["High (top 10%)", "Medium (next 40%)", "Low (bottom 50%)"])
            ax.set_title(f"{net}: {tgt}, WAPE % by zone-demand tier")
    axes[0, 0].legend(ncol=4, fontsize=8)
    fig.suptitle(f"Error grows sharply for low-demand zones ({eval_set.replace('_', ' ')}, one-step)",
                 fontweight="bold")
    return _save(fig, f"phase3_tier_wape_{eval_set}.png")


def fig_fc_post_break(pred: pd.DataFrame, selection: pd.DataFrame, gran: str = "W") -> Path:
    """Network units/orders after the break: naive horizon vs adapted forecasts vs actual."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 6.5))
    for i, tgt in enumerate(["orders", "units"]):
        for j, net in enumerate(FC_NETS):
            mdl = "xgboost"  # the ML reference shown in every panel; regime-reset lines are added below
            ax = axes[i, j]
            base = pred[(pred["granularity"] == gran) & (pred["target"] == tgt) & (pred["network"] == net)]
            pre_hist = base[(base["eval_set"] == "pre_break_test") & (base["mode"] == "one_step")
                            & (base["model"] == "historical_average")].groupby("period_start")["actual"].sum()
            post = base[base["eval_set"] == "post_break_test"]
            act = post[(post["mode"] == "one_step") & (post["model"] == "historical_average")].groupby("period_start")["actual"].sum()
            a = pd.concat([pre_hist, act])
            ax.plot(a.index, a.values, color=INK, lw=2.2, label="Actual")
            naive = post[(post["mode"] == "horizon") & (post["model"] == mdl)].groupby("period_start")["predicted"].sum()
            ax.plot(naive.index, naive.values, color=MODEL_COLORS[mdl], lw=1.5, ls=":",
                    label=f"{MODEL_LABELS[mdl]}: horizon from 2017-09-30 (no post-break data)")
            ad = base[base["eval_set"] == "post_break_adapted"]
            for hd, ls in [("none", "--"), ("recalibrated", "-")]:
                s = ad[(ad["model"] == mdl) & (ad["handling"] == hd)].groupby("period_start")["predicted"].sum()
                ax.plot(s.index, s.values, color=MODEL_COLORS[mdl], lw=1.8, ls=ls,
                        label=f"{MODEL_LABELS[mdl]}: after 4 post-break weeks, {'raw' if hd == 'none' else 'recalibrated'}")
            for rm, ls in [("share_x_recent_level", "-"), ("post_break_average", (0, (4, 3)))]:
                s = ad[ad["model"] == rm].groupby("period_start")["predicted"].sum()
                ax.plot(s.index, s.values, color=MODEL_COLORS[rm], lw=1.8, ls=ls,
                        label=MODEL_LABELS[rm] + (" (same network total; differs only by zone)"
                                                  if rm == "post_break_average" else ""))
            sel = selection[(selection["target"] == tgt) & (selection["network"] == net)].iloc[0]
            ax.text(0.99, 0.02, f"selected: {MODEL_LABELS.get(sel['model'], sel['model'])} ({sel['handling']})",
                    transform=ax.transAxes, ha="right", fontsize=7, color=MUTED)
            ax.axvline(pd.Timestamp("2017-10-01"), color=MUTED, ls="--", lw=1)
            ax.set_title(f"{net}: weekly {tgt}, network total")
            ax.tick_params(axis="x", rotation=30)
    axes[0, 0].legend(fontsize=6.5, loc="upper left")
    fig.suptitle("The October 2017 break: forecasts that never saw post-break data vs adapted forecasts",
                 fontweight="bold")
    return _save(fig, "phase3_post_break_adaptation.png")


def fig_fc_importance(imp: pd.DataFrame, top: int = 12) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for i, tgt in enumerate(["orders", "units"]):
        for j, (model, kind, title) in enumerate([("xgboost", "gain", "XGBoost gain share"),
                                                  ("xgboost", "permutation_mae_increase",
                                                   "XGBoost permutation (MAE increase, pre-break test)")]):
            ax = axes[i, j]
            g = imp[(imp["target"] == tgt) & (imp["model"] == model) & (imp["importance_type"] == kind)
                    & (imp["granularity"] == "W")].nlargest(top, "importance")[::-1]
            ax.barh(g["feature"], g["importance"], color="#2a78d6", height=0.7)
            ax.set_title(f"{tgt}: {title}", fontsize=10)
    fig.suptitle("What drives the XGBoost forecasts: recent zone demand dominates; calendar adds little",
                 fontweight="bold")
    return _save(fig, "phase3_feature_importance.png")


def fig_fc_zone_scatter(pred: pd.DataFrame, selection: pd.DataFrame, gran: str = "W") -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    for ax, tgt in zip(axes, ["orders", "units"]):
        parts, labels = [], []
        for net in FC_NETS:
            sel = selection[(selection["target"] == tgt) & (selection["network"] == net)].iloc[0]
            p = pred[(pred["granularity"] == gran) & (pred["eval_set"] == "post_break_adapted")
                     & (pred["model"] == sel["model"]) & (pred["handling"] == sel["handling"])
                     & (pred["target"] == tgt) & (pred["network"] == net)]
            g = p.groupby("zone_id")[["actual", "predicted"]].sum().reset_index().assign(network=net)
            parts.append(g)
            ax.scatter(g["actual"] + 0.5, g["predicted"] + 0.5, s=14, alpha=0.6, color=NET_COLORS[net],
                       label=f"{net}: {MODEL_LABELS.get(sel['model'], sel['model'])} ({sel['handling']})")
        zt = pd.concat(parts)
        lim = [0.4, zt[["actual", "predicted"]].values.max() * 1.6]
        ax.plot(lim, lim, color=MUTED, ls=":", lw=1)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
        ax.set_xlabel("actual zone total over test window (+0.5)"); ax.set_ylabel("forecast zone total (+0.5)")
        ax.set_title(f"{tgt}: selected model per network, 13-week zone totals", fontsize=10)
        ax.legend(fontsize=7)
    fig.suptitle("Zone-level horizon totals: the quantity the CFLP consumes", fontweight="bold")
    return _save(fig, "phase3_zone_total_scatter.png")


def fig_fc_granularity(evaluation: pd.DataFrame) -> Path:
    e = evaluation[(evaluation["tier"] == "all") & (evaluation["level"] == "zone_total")
                   & evaluation["network"].isin(FC_NETS) & (evaluation["mode"] == "horizon")
                   & (evaluation["handling"] == "none") & evaluation["eval_set"].isin(["pre_break_test", "post_break_test"])
                   & evaluation["model"].isin(ALL_FC_MODELS)]
    fig, axes = plt.subplots(1, 4, figsize=(15, 4), sharey=True)
    combos = [(t, es) for t in ["orders", "units"] for es in ["pre_break_test", "post_break_test"]]
    w = 0.2
    for ax, (tgt, es) in zip(axes, combos):
        for k, m in enumerate(ALL_FC_MODELS):
            vals = []
            for gran in ["W", "M"]:
                v = e[(e["target"] == tgt) & (e["eval_set"] == es) & (e["model"] == m) & (e["granularity"] == gran)
                      & (e["network"] == "CONUS")]["WAPE"]
                vals.append(float(v.iloc[0]) if len(v) else np.nan)
            ax.bar(np.arange(2) + (k - 1.5) * w, 100 * np.array(vals), width=w - 0.02, color=MODEL_COLORS[m],
                   label=MODEL_LABELS[m])
        ax.set_xticks([0, 1], ["Weekly model", "Monthly model"])
        ax.set_title(f"CONUS {tgt}\n{es.replace('_', ' ')}", fontsize=10)
    axes[0].set_ylabel("zone-total WAPE % over the 4-month window")
    axes[0].legend(fontsize=7)
    fig.suptitle("Weekly vs monthly aggregation, compared on the same quantity (zone totals over the test window)",
                 fontweight="bold")
    return _save(fig, "phase3_weekly_vs_monthly.png")


def fig_fc_cflp_map(cflp: pd.DataFrame) -> Path:
    z = cflp.rename(columns={"forecast_per_period_orders": "units"})  # reuse bubble helper on orders
    z = z.assign(zone_id=cflp["zone_id"])
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [2.2, 1]})
    for ax, net, top in [(axes[0], "CONUS", 10), (axes[1], "Puerto Rico", 4)]:
        g = z[z["network"] == net]
        ax.scatter(g["centroid_lon"], g["centroid_lat"], s=_bubble(g["units"], 900 if net == "CONUS" else 1200),
                   color=NET_COLORS[net], alpha=0.55, edgecolor="#fcfcfb", linewidth=0.8)
        for r in g.nlargest(top, "units").itertuples():
            name = r.dominant_city if net == "CONUS" else r.zone_id
            ax.annotate(f"{name}\n{r.units:.1f}/wk", (r.centroid_lon, r.centroid_lat), fontsize=7,
                        xytext=(5, 5), textcoords="offset points")
        _geo_aspect(ax, g["centroid_lat"].mean())
        ax.set_title(f"{net}: forecast orders/week per zone (bubble area)", fontsize=10)
    f0, f1 = cflp["forecast_start"].iat[0], cflp["forecast_end"].iat[0]
    fig.suptitle(f"CFLP demand input: forecast orders/week by zone, {f0} to {f1} (model per network in report)",
                 fontweight="bold")
    return _save(fig, "phase3_cflp_demand_forecast_map.png")


def make_phase3_figures(pred_w, pred_all, evaluation, imp, selection, cflp) -> list[Path]:
    return [fig_fc_network_series(pred_w), fig_fc_wape(evaluation, "W"), fig_fc_wape(evaluation, "M"),
            fig_fc_tiers(evaluation, "pre_break_test"), fig_fc_tiers(evaluation, "post_break_test"),
            fig_fc_post_break(pred_w, selection), fig_fc_importance(imp), fig_fc_zone_scatter(pred_w, selection),
            fig_fc_granularity(evaluation), fig_fc_cflp_map(cflp)]
