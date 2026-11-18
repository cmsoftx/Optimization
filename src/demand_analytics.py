"""Phase 2: historical demand analytics on the cleaned, zoned demand set.

Every function takes the Phase 2 tables (orders, zones, zone-day demand, items)
and returns a tidy DataFrame. ``build_eda_summary`` collects the headline
metrics into ``eda_summary.csv``, with each value's provenance
(``dataset`` = directly counted, ``derived`` = computed statistic,
``modelling choice`` = depends on a configured parameter).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, spearmanr

from .config import get_path, load_config

PRE, POST = "pre_2017_10", "post_2017_10"


def _demand(orders: pd.DataFrame) -> pd.DataFrame:
    return orders[orders["in_demand_set"]]


def monthly_by_network(orders: pd.DataFrame) -> pd.DataFrame:
    o = _demand(orders)
    return (o.groupby(["network", o["order_date"].dt.to_period("M").astype(str).rename("month")])
             .agg(orders=("order_id", "size"), units=("units", "sum"), items=("n_items", "sum"),
                  sales=("sales", "sum"), customers=("customer_id", "nunique"))
             .reset_index())


def weekly_by_network(orders: pd.DataFrame) -> pd.DataFrame:
    """ISO weeks (Mon-Sun). The first and last weeks are partial and flagged."""
    o = _demand(orders)
    wk = o["order_date"].dt.to_period("W-SUN")
    out = (o.groupby(["network", wk.rename("week")])
             .agg(orders=("order_id", "size"), units=("units", "sum"), days=("order_date", "nunique"))
             .reset_index())
    out["week_start"] = out["week"].dt.start_time
    out["partial_week"] = out["days"] < 7
    out["week"] = out["week"].astype(str)
    return out


def day_of_week_profile(orders: pd.DataFrame) -> pd.DataFrame:
    """Mean orders/units per calendar day by weekday, network and regime."""
    o = _demand(orders)
    days = pd.date_range(o["order_date"].min(), o["order_date"].max(), freq="D")
    brk = pd.Timestamp(load_config()["preprocessing"]["regime_break_date"])
    grid = pd.MultiIndex.from_product([sorted(o["network"].unique()), days], names=["network", "order_date"])
    daily = (o.groupby(["network", "order_date"]).agg(orders=("order_id", "size"), units=("units", "sum"))
              .reindex(grid, fill_value=0).reset_index())  # zero-filled calendar
    daily["regime"] = np.where(daily["order_date"] >= brk, POST, PRE)
    daily["weekday"] = daily["order_date"].dt.day_name()
    out = daily.groupby(["network", "regime", "weekday"])[["orders", "units"]].mean().reset_index()
    out["index_vs_mean"] = out["orders"] / out.groupby(["network", "regime"])["orders"].transform("mean")
    return out


def regime_calendar_days(orders: pd.DataFrame, regime: str) -> int:
    """Number of calendar days in a regime window of the demand set."""
    brk = pd.Timestamp(load_config()["preprocessing"]["regime_break_date"])
    lo, hi = orders["order_date"].min(), orders["order_date"].max()
    if regime == PRE:
        return int((brk - lo).days)
    return int((hi - brk).days + 1)


def regime_comparison(orders: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side statistics before and after the 2017-10 break, per network."""
    o, it = _demand(orders), items[items["in_demand_set"]]
    rows = []
    for net, g in o.groupby("network"):
        pre, post = g[g["regime"] == PRE], g[g["regime"] == POST]
        ipre, ipost = it[(it["network"] == net) & (it["regime"] == PRE)], it[(it["network"] == net) & (it["regime"] == POST)]
        for reg, d, di in [(PRE, pre, ipre), (POST, post, ipost)]:
            # Calendar days of the regime window (not days with orders: sparse networks such as
            # Hawaii have many zero-order days).
            ndays = regime_calendar_days(o, reg)
            rows.append({
                "network": net, "regime": reg, "first_day": d["order_date"].min().date(),
                "last_day": d["order_date"].max().date(), "calendar_days": ndays,
                "days_with_orders": d["order_date"].nunique(),
                "orders": len(d), "units": int(d["units"].sum()),
                "orders_per_day": len(d) / ndays, "units_per_day": d["units"].sum() / ndays,
                "items_per_order": d["n_items"].mean(), "units_per_order": d["units"].mean(),
                "units_per_item": di["order_item_quantity"].mean(),
                "sales_per_order": d["sales"].mean(),
                "customers": d["customer_id"].nunique(),
                "share_customers_seen_before_break": (d["customer_id"].isin(pre["customer_id"]).mean()
                                                      if reg == POST else np.nan),
                "categories": di["category_name"].nunique(),
                "top_category": di["category_name"].value_counts().idxmax() if len(di) else None,
                "markets": d["market"].nunique(),
            })
    return pd.DataFrame(rows)


def category_by_regime(items: pd.DataFrame) -> pd.DataFrame:
    """Unit share of each category within (network, regime)."""
    it = items[items["in_demand_set"]]
    c = it.groupby(["network", "regime", "category_name"])["order_item_quantity"].sum().rename("units").reset_index()
    c["unit_share"] = c["units"] / c.groupby(["network", "regime"])["units"].transform("sum")
    return c.sort_values(["network", "regime", "units"], ascending=[True, True, False])


def zone_spatial_stability(zone_daily: pd.DataFrame) -> pd.DataFrame:
    """Does the spatial demand pattern survive the regime change?

    Compares each zone's share of network ORDERS before vs after the break
    (orders, not units, because units/order changed by about 6x). Reports
    Spearman rank correlation and the mean absolute share difference.
    """
    rows = []
    for net, g in zone_daily.groupby("network"):
        s = g.groupby(["zone_id", "regime"])["orders"].sum().unstack(fill_value=0)
        if PRE not in s or POST not in s:
            continue
        share = s / s.sum()
        rho, p = spearmanr(share[PRE], share[POST]) if len(share) > 2 else (np.nan, np.nan)
        rows.append({"network": net, "zones": len(share), "spearman_rho_zone_order_share": rho,
                     "p_value": p, "mean_abs_share_diff_pp": 100 * (share[PRE] - share[POST]).abs().mean(),
                     "pearson_r": share[PRE].corr(share[POST])})
    return pd.DataFrame(rows)


def zone_concentration(zones: pd.DataFrame) -> pd.DataFrame:
    """Pareto curve: cumulative unit share vs cumulative zone share."""
    parts = []
    for net, g in zones.groupby("network"):
        s = g.sort_values("units", ascending=False)
        parts.append(pd.DataFrame({
            "network": net, "zone_id": s["zone_id"].values, "rank": np.arange(1, len(s) + 1),
            "zone_share_cum": np.arange(1, len(s) + 1) / len(s),
            "units_share_cum": s["units"].cumsum().values / s["units"].sum(),
        }))
    return pd.concat(parts, ignore_index=True)


def gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return float("nan")
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def demand_sparsity(zone_daily: pd.DataFrame) -> pd.DataFrame:
    """Share of zero-demand periods at daily, weekly and monthly granularity.

    This drives the forecasting granularity decision in Phase 3.
    """
    rows = []
    zd = zone_daily
    for freq, label in [("D", "day"), ("W-SUN", "week"), ("M", "month")]:
        per = zd["date"].dt.to_period(freq)
        agg = zd.groupby(["network", "zone_id", per])["orders"].sum().reset_index()
        for net, g in agg.groupby("network"):
            rows.append({"network": net, "granularity": label, "zone_periods": len(g),
                         "zero_share": (g["orders"] == 0).mean(), "mean_orders": g["orders"].mean(),
                         "median_orders": g["orders"].median()})
    return pd.DataFrame(rows)


def destination_independence(orders: pd.DataFrame) -> pd.DataFrame:
    """Chi-square tests: is 'domestic destination' independent of customer location?

    If destinations were real deliveries, US customers would mostly have US
    destinations, and the share would vary strongly by state/network.
    """
    o = _demand(orders)
    rows = []
    for name, key in [("network", o["network"]), ("customer_state (CONUS)", None)]:
        d = o if key is not None else o[o["network"] == "CONUS"]
        k = key if key is not None else d["customer_state"]
        tab = pd.crosstab(k, d["destination_domestic"])
        chi2, p, dof, _ = chi2_contingency(tab)
        cramers_v = np.sqrt(chi2 / (tab.values.sum() * (min(tab.shape) - 1)))
        rows.append({"test": f"destination_domestic vs {name}", "chi2": chi2, "dof": dof, "p_value": p,
                     "cramers_v": cramers_v, "overall_domestic_share": d["destination_domestic"].mean()})
    return pd.DataFrame(rows)


def shipping_mode_mix(orders: pd.DataFrame) -> pd.DataFrame:
    o = _demand(orders)
    out = (o.groupby(["network", "shipping_mode"])
             .agg(orders=("order_id", "size"), real_days=("days_for_shipping_real", "mean"),
                  scheduled_days=("days_for_shipment_scheduled", "mean"), late_risk=("late_delivery_risk", "mean"))
             .reset_index())
    out["order_share"] = out["orders"] / out.groupby("network")["orders"].transform("sum")
    return out


def high_low_zones(zones: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = ["network", "zone_id", "dominant_city", "dominant_state", "n_customers", "n_orders", "units",
            "share_of_network_units", "centroid_lat", "centroid_lon"]
    parts = []
    for net, g in zones.groupby("network"):
        hi = g.nlargest(n, "units").assign(tier="high")
        lo = g.nsmallest(n, "units").assign(tier="low")
        parts += [hi, lo]
    return pd.concat(parts)[["tier"] + cols]


def build_eda_summary(items, orders, zones, zone_daily, tables: dict) -> pd.DataFrame:
    """Headline metrics with provenance."""
    rows = []

    def add(scope, metric, value, unit="", source="dataset"):
        rows.append({"scope": scope, "metric": metric, "value": value, "unit": unit, "source": source})

    add("raw", "order-item rows", len(items), "rows")
    add("raw", "orders", items["order_id"].nunique(), "orders")
    add("raw", "customers", items["customer_id"].nunique(), "customers")
    di = items[items["in_demand_set"]]
    add("demand set", "order-item rows", len(di), "rows")
    add("demand set", "orders (deliveries)", di["order_id"].nunique(), "orders")
    add("demand set", "units", int(di["order_item_quantity"].sum()), "units")
    add("demand set", "share of raw units retained", di["order_item_quantity"].sum() / items["order_item_quantity"].sum(), "ratio", "derived")
    add("demand set", "date range", f"{di['order_date'].min().date()} to {di['order_date'].max().date()}")
    o = _demand(orders)
    conc = tables["concentration"]
    for net, g in o.groupby("network"):
        z = zones[zones["network"] == net]
        add(net, "orders", len(g), "orders")
        add(net, "units", int(g["units"].sum()), "units")
        add(net, "customers", g["customer_id"].nunique(), "customers")
        add(net, "unique coordinates", int(z["n_coordinates"].sum()), "points")
        add(net, "demand zones", len(z), "zones", "modelling choice")
        add(net, "zone diameter limit", load_config()["demand_zones"]["max_diameter_km"][net], "km", "modelling choice")
        add(net, "zone units Gini", gini(z["units"].values), "0-1", "derived")
        c = conc[conc["network"] == net]
        add(net, "zones needed for 80% of units", int((c["units_share_cum"] < 0.8).sum() + 1), "zones", "derived")
        top = z.nlargest(1, "units").iloc[0]
        add(net, "largest zone", f"{top['zone_id']} ({top['dominant_city']}, {top['dominant_state']})", "", "derived")
        add(net, "largest zone unit share", top["share_of_network_units"], "ratio", "derived")
        m = g[g["regime"] == PRE].groupby(g["order_date"].dt.to_period("M"))["units"].sum()
        add(net, "monthly units CV (pre-break)", m.std() / m.mean(), "ratio", "derived")
    rc = tables["regime"]
    for r in rc.itertuples():
        for k in ["orders_per_day", "units_per_day", "units_per_order", "items_per_order", "categories"]:
            add(f"{r.network} | {r.regime}", k, getattr(r, k), "", "derived")
        if r.regime == POST:
            add(f"{r.network} | {r.regime}", "share of customers seen before break",
                r.share_customers_seen_before_break, "ratio", "derived")
    dow = tables["dow"]
    for (net, reg), g in dow.groupby(["network", "regime"]):
        add(f"{net} | {reg}", "weekday orders index range (max-min)",
            g["index_vs_mean"].max() - g["index_vs_mean"].min(), "ratio", "derived")
    for r in tables["stability"].itertuples():
        add(r.network, "zone order-share Spearman rho pre vs post", r.spearman_rho_zone_order_share, "", "derived")
    for r in tables["sparsity"].itertuples():
        add(r.network, f"zero-demand share per zone-{r.granularity}", r.zero_share, "ratio", "derived")
    for r in tables["destination"].itertuples():
        add("destination", f"{r.test}: Cramer's V", r.cramers_v, "", "derived")
        add("destination", f"{r.test}: p-value", r.p_value, "", "derived")
    return pd.DataFrame(rows)


def run_demand_analytics(items, orders, zones, zone_daily, write: bool = True) -> dict:
    tables = {
        "monthly": monthly_by_network(orders),
        "weekly": weekly_by_network(orders),
        "dow": day_of_week_profile(orders),
        "regime": regime_comparison(orders, items),
        "category": category_by_regime(items),
        "stability": zone_spatial_stability(zone_daily),
        "concentration": zone_concentration(zones),
        "sparsity": demand_sparsity(zone_daily),
        "destination": destination_independence(orders),
        "shipping": shipping_mode_mix(orders),
        "high_low": high_low_zones(zones),
    }
    tables["summary"] = build_eda_summary(items, orders, zones, zone_daily, tables)
    if write:
        out = get_path("outputs_dir")
        tables["summary"].to_csv(out / "eda_summary.csv", index=False)
        names = {"monthly": "eda_monthly_demand_by_network", "weekly": "eda_weekly_demand_by_network",
                 "dow": "eda_day_of_week_profile", "regime": "eda_regime_comparison",
                 "category": "eda_category_demand_by_regime", "stability": "eda_zone_spatial_stability",
                 "concentration": "eda_zone_concentration", "sparsity": "eda_demand_sparsity",
                 "destination": "eda_destination_independence", "shipping": "eda_shipping_mode_mix",
                 "high_low": "eda_high_low_demand_zones"}
        for k, name in names.items():
            tables[k].to_csv(out / f"{name}.csv", index=False)
    return tables
