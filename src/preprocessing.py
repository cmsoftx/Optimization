"""Phase 2: cleaning, network scoping, demand zones and demand aggregation.

Pipeline (each step is logged to ``data_quality_report.csv``)
-------------------------------------------------------------
1.  Load the raw order-item table. The raw file is opened read-only and never modified.
2.  Drop PII and non-informative columns; rename to snake_case.
3.  Validate dates and duplicates.
4.  Flag non-demand orders (CANCELED / SUSPECTED_FRAUD never ship).
5.  Flag invalid coordinates (Phase 1 rules) and map the remaining
    coordinates to a logistics network (CONUS / Puerto Rico / Hawaii).
6.  Flag the 2017-10 regime change and domestic vs international destination.
7.  Build demand zones per network (complete-linkage clustering, bounded
    diameter) on validated customer coordinates.
8.  Aggregate: order-item rows -> orders (deliveries) -> zone x day demand.
9.  Reconcile every aggregation level (units, orders, sales must match).

Outputs (``data/processed``): ``cleaned_data.csv`` (item level, PII-free),
``orders.csv``, ``demand_zones.csv``, ``zone_daily_demand.csv``,
``network_category_daily_demand.csv``.
Outputs (``data/outputs``): ``data_quality_report.csv``,
``phase2_aggregation_reconciliation.csv``, ``phase2_coordinate_validation.csv``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage

from .config import get_path, load_config
from .data_inspection import COORD_FLAGS, coordinate_flags
from .data_loader import load_raw_orders
from .distance_calculator import EARTH_RADIUS_KM, haversine_km

log = logging.getLogger(__name__)


# Cleaning-decision log
@dataclass
class CleaningLog:
    """Accumulates one row per cleaning decision for data_quality_report.csv."""
    rows: list[dict] = field(default_factory=list)

    def add(self, step: str, rule: str, action: str, rationale: str,
            records: int = 0, orders: int = 0, units: int = 0,
            remaining_records: int | None = None, remaining_orders: int | None = None) -> None:
        self.rows.append({
            "step": len(self.rows) + 1, "stage": step, "rule": rule, "action": action,
            "records_affected": int(records), "orders_affected": int(orders), "units_affected": int(units),
            "records_remaining_in_demand_set": remaining_records,
            "orders_remaining_in_demand_set": remaining_orders, "rationale": rationale,
        })

    def frame(self) -> pd.DataFrame:
        f = pd.DataFrame(self.rows)
        for c in ["records_remaining_in_demand_set", "orders_remaining_in_demand_set"]:
            f[c] = f[c].astype("Int64")
        return f


def to_snake(name: str) -> str:
    """'Days for shipping (real)' -> 'days_for_shipping_real'."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    return s


RENAME_OVERRIDES = {  # clearer names for two awkward raw columns
    "order date (DateOrders)": "order_datetime",
    "shipping date (DateOrders)": "shipping_datetime",
}


# Step 1-6: cleaning and flagging (item level)
def clean_items(raw: pd.DataFrame, clog: CleaningLog) -> pd.DataFrame:
    """Return the PII-free, flagged item-level table. No rows are deleted here;
    rows are *flagged* so every exclusion stays auditable."""
    cfg = load_config()
    pp = cfg["preprocessing"]
    df = raw.copy()
    n0 = len(df)

    def _counts(mask: pd.Series) -> tuple[int, int, int]:
        return int(mask.sum()), int(df.loc[mask, "Order Id"].nunique()), int(df.loc[mask, "Order Item Quantity"].sum())

    clog.add("load", "Read raw DataCoSupplyChainDataset.csv (Latin-1)", "none",
             "Raw file is opened read-only and never modified.", records=n0,
             orders=df["Order Id"].nunique(), units=df["Order Item Quantity"].sum(),
             remaining_records=n0, remaining_orders=df["Order Id"].nunique())

    # columns -----------------------------------------------------------
    pii = [c for c in cfg["dataset"]["pii_columns"] if c in df.columns]
    df = df.drop(columns=pii)
    clog.add("privacy", f"Drop PII columns: {', '.join(pii)}", "drop columns",
             "Names and street addresses identify people. Email/password are masked but are dropped too.",
             records=n0)
    drops = {c: why for c, why in pp["drop_columns"].items() if c in df.columns}
    df = df.drop(columns=list(drops))
    for c, why in drops.items():
        clog.add("columns", f"Drop column '{c}'", "drop column", why, records=n0)
    rename = {c: RENAME_OVERRIDES.get(c, to_snake(c)) for c in df.columns}
    df = df.rename(columns=rename)
    clog.add("columns", "Rename columns to snake_case", "rename",
             "Stable programmatic names. The mapping is in data/outputs/phase2_column_mapping.csv.", records=0)
    pd.DataFrame({"raw_column": list(rename), "clean_column": list(rename.values())}).to_csv(
        get_path("outputs_dir") / "phase2_column_mapping.csv", index=False)

    # dates / duplicates ------------------------------------------------
    bad_dates = df["order_datetime"].isna() | df["shipping_datetime"].isna()
    clog.add("validity", "Unparseable order/shipping date", "would exclude", "No failures found.",
             records=bad_dates.sum())
    dups = df.duplicated()
    clog.add("validity", "Exact duplicate rows", "would exclude", "No duplicates found.", records=dups.sum())
    df = df[~bad_dates & ~dups].copy()

    df["order_date"] = df["order_datetime"].dt.normalize()

    # non-demand orders -------------------------------------------------
    df["is_demand"] = ~df["order_status"].isin(pp["non_demand_order_statuses"])
    m = ~df["is_demand"]
    r, o, u = int(m.sum()), int(df.loc[m, "order_id"].nunique()), int(df.loc[m, "order_item_quantity"].sum())
    keep = df["is_demand"]
    clog.add("demand definition", f"Order Status in {pp['non_demand_order_statuses']}", "exclude from demand",
             "These orders never ship (Delivery Status = 'Shipping canceled'), so they are not physical demand. "
             "The rows stay in cleaned_data with is_demand=False.",
             records=r, orders=o, units=u, remaining_records=int(keep.sum()),
             remaining_orders=int(df.loc[keep, "order_id"].nunique()))

    # coordinates & networks -------------------------------------------
    flag_input = df.rename(columns={"customer_id": "Customer Id", "customer_city": "Customer City",
                                    "customer_state": "Customer State", "customer_country": "Customer Country",
                                    "latitude": "Latitude", "longitude": "Longitude"})
    flags = coordinate_flags(flag_input)
    df["coord_region"] = flags["region"].values
    df["coord_valid"] = ~flags["any_flag"].values
    df["coord_issue"] = flags[COORD_FLAGS].apply(lambda r: ";".join(r.index[r.values]), axis=1).values
    m = keep & ~df["coord_valid"]
    keep &= df["coord_valid"]
    clog.add("geography", "Coordinate fails any Phase 1 check (sign flip, truncated longitude, placeholder, "
             ">1000 km from state median, PR/mainland conflict)", "exclude from spatial demand",
             "Not corrected: the true location cannot be recovered reliably. Imputing a city median would "
             "invent locations.", records=m.sum(), orders=df.loc[m, "order_id"].nunique(),
             units=df.loc[m, "order_item_quantity"].sum(), remaining_records=int(keep.sum()),
             remaining_orders=int(df.loc[keep, "order_id"].nunique()))

    net_map = cfg["networks"]
    df["network"] = df["coord_region"].where(df["coord_region"].isin(list(net_map)), "Excluded")
    df.loc[~df["coord_valid"], "network"] = "Excluded"
    m = keep & df["network"].eq("Excluded")
    keep &= df["network"].ne("Excluded")
    clog.add("geography", "Valid coordinate outside CONUS / Puerto Rico / Hawaii", "exclude from spatial demand",
             "No logistics network is defined for that region.", records=m.sum(),
             orders=df.loc[m, "order_id"].nunique(), units=df.loc[m, "order_item_quantity"].sum(),
             remaining_records=int(keep.sum()), remaining_orders=int(df.loc[keep, "order_id"].nunique()))
    for net, spec in net_map.items():
        mm = keep & df["network"].eq(net)
        clog.add("network scope", f"Assign to network '{net}'", "label",
                 f"Role: {spec['role']}.", records=mm.sum(), orders=df.loc[mm, "order_id"].nunique(),
                 units=df.loc[mm, "order_item_quantity"].sum())

    # regime / destination flags ----------------------------------------
    brk = pd.Timestamp(pp["regime_break_date"])
    df["regime"] = np.where(df["order_datetime"] >= brk, "post_2017_10", "pre_2017_10")
    mm = keep & df["regime"].eq("post_2017_10")
    clog.add("temporal", f"order_datetime >= {brk.date()}", "label regime='post_2017_10'",
             "The data-generating process changes here (Phase 1). Rows are kept and labelled so that "
             "forecasting can model the change explicitly.", records=mm.sum(),
             orders=df.loc[mm, "order_id"].nunique(), units=df.loc[mm, "order_item_quantity"].sum())

    df["destination_domestic"] = df["order_country"].isin(pp["domestic_destination_countries"])
    mm = keep & ~df["destination_domestic"]
    if pp["destination_scope"] == "domestic_only":
        keep &= df["destination_domestic"]
        action, why = "exclude from demand", "destination_scope=domestic_only."
    else:
        action = "label only (demand stays at customer coordinate)"
        why = ("Approved scope: demand is located at the customer coordinate. International Order Country "
               "values are never routed. Their share is the same in every network (see coordinate validation), "
               "so the field is not geographically linked to the customer.")
    clog.add("network scope", "Order Country is international", action, why, records=mm.sum(),
             orders=df.loc[mm, "order_id"].nunique(), units=df.loc[mm, "order_item_quantity"].sum(),
             remaining_records=int(keep.sum()), remaining_orders=int(df.loc[keep, "order_id"].nunique()))

    df["in_demand_set"] = keep
    return df


# Step 7: demand zones
def _unit_vectors(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def build_zones(points: pd.DataFrame, max_diameter_km: float, prefix: str) -> pd.DataFrame:
    """Cluster unique coordinates into zones of bounded diameter.

    Complete linkage on chord distance (a monotone function of great-circle
    distance) ensures that, inside every zone, *every pair* of coordinates is
    at most ``max_diameter_km`` apart (great-circle). The method is deterministic.

    Parameters
    ----------
    points : one row per unique coordinate with columns latitude, longitude, weight.
    Returns ``points`` with a ``zone_id`` column. IDs are ranked by total weight.
    """
    pts = points.reset_index(drop=True).copy()
    if len(pts) == 1:
        pts["zone_raw"] = 1
    else:
        xyz = _unit_vectors(pts["latitude"].to_numpy(), pts["longitude"].to_numpy())
        chord = 2.0 * np.sin(max_diameter_km / (2.0 * EARTH_RADIUS_KM))  # on the unit sphere
        Z = linkage(xyz, method="complete", metric="euclidean")
        pts["zone_raw"] = fcluster(Z, t=chord, criterion="distance")
    order = pts.groupby("zone_raw")["weight"].sum().sort_values(ascending=False, kind="mergesort")
    rank = {z: i + 1 for i, z in enumerate(order.index)}
    pts["zone_id"] = pts["zone_raw"].map(rank).map(lambda i: f"{prefix}-Z{i:03d}")
    return pts.drop(columns="zone_raw")


def assign_zones(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assign every item in the demand set to a zone; return items and the zone table."""
    cfg = load_config()
    diam = cfg["demand_zones"]["max_diameter_km"]
    d = items[items["in_demand_set"]]
    coords = (d.groupby(["network", "latitude", "longitude"])["order_item_quantity"].sum()
               .rename("weight").reset_index())
    parts = []
    for net, g in coords.groupby("network"):
        parts.append(build_zones(g, float(diam[net]), cfg["networks"][net]["code"]))
    coord_zone = pd.concat(parts, ignore_index=True)[["network", "latitude", "longitude", "zone_id"]]
    items = items.merge(coord_zone, on=["network", "latitude", "longitude"], how="left")
    # Only demand rows get a zone; cancelled orders at the same coordinate must not carry one.
    items.loc[~items["in_demand_set"], "zone_id"] = np.nan
    zones = zone_table(items[items["in_demand_set"]])
    return items, zones


def zone_table(d: pd.DataFrame) -> pd.DataFrame:
    """Zone attributes: unit-weighted centroid, size, dominant city/state, spread."""
    g = d.groupby("zone_id")
    w = d["order_item_quantity"]
    cen = pd.DataFrame({
        "centroid_lat": (d["latitude"] * w).groupby(d["zone_id"]).sum() / w.groupby(d["zone_id"]).sum(),
        "centroid_lon": (d["longitude"] * w).groupby(d["zone_id"]).sum() / w.groupby(d["zone_id"]).sum(),
    })
    z = g.agg(network=("network", "first"), n_customers=("customer_id", "nunique"),
              n_coordinates=("latitude", lambda s: d.loc[s.index, ["latitude", "longitude"]].drop_duplicates().shape[0]),
              n_orders=("order_id", "nunique"), units=("order_item_quantity", "sum"), sales=("sales", "sum"),
              first_order=("order_date", "min"), last_order=("order_date", "max"))
    z = z.join(cen)
    dom = (d.groupby(["zone_id", "customer_state", "customer_city"])["order_item_quantity"].sum()
             .reset_index().sort_values(["zone_id", "order_item_quantity"], ascending=[True, False])
             .drop_duplicates("zone_id").set_index("zone_id"))
    z["dominant_state"] = dom["customer_state"]
    z["dominant_city"] = dom["customer_city"]
    # spread: max distance from centroid over unique member coordinates
    u = d[["zone_id", "latitude", "longitude"]].drop_duplicates().join(z[["centroid_lat", "centroid_lon"]], on="zone_id")
    u["km"] = haversine_km(u["latitude"], u["longitude"], u["centroid_lat"], u["centroid_lon"])
    z["max_km_from_centroid"] = u.groupby("zone_id")["km"].max()
    z["share_of_network_units"] = z["units"] / z.groupby("network")["units"].transform("sum")
    brk = pd.Timestamp(load_config()["preprocessing"]["regime_break_date"])
    lo, hi = d["order_date"].min(), d["order_date"].max()
    cal_days = {"pre_2017_10": (brk - lo).days, "post_2017_10": (hi - brk).days + 1}
    for reg in ["pre_2017_10", "post_2017_10"]:
        dd = d[d["regime"] == reg]
        ndays = max(cal_days[reg], 1)  # calendar days, so zero-order days count
        z[f"units_per_day_{reg}"] = dd.groupby("zone_id")["order_item_quantity"].sum().reindex(z.index).fillna(0) / ndays
        z[f"orders_per_day_{reg}"] = dd.groupby("zone_id")["order_id"].nunique().reindex(z.index).fillna(0) / ndays
    return z.reset_index().sort_values(["network", "zone_id"]).reset_index(drop=True)


# Step 8: aggregation
def aggregate_orders(items: pd.DataFrame) -> pd.DataFrame:
    """One row per order (= one delivery). Order-level attributes are constant
    within an order (verified in Phase 1), so ``first`` is safe."""
    first = ["customer_id", "order_datetime", "order_date", "shipping_datetime", "network", "zone_id",
             "latitude", "longitude", "customer_city", "customer_state", "customer_segment", "market",
             "order_region", "order_country", "destination_domestic", "shipping_mode", "order_status",
             "delivery_status", "late_delivery_risk", "days_for_shipping_real", "days_for_shipment_scheduled",
             "regime", "is_demand", "coord_valid", "in_demand_set", "type"]
    agg = {c: (c, "first") for c in first}
    agg.update(n_items=("order_item_id", "size"), units=("order_item_quantity", "sum"),
               sales=("sales", "sum"), order_total=("order_item_total", "sum"),
               discount=("order_item_discount", "sum"), profit=("order_profit_per_order", "sum"),
               n_categories=("category_name", "nunique"),
               main_category=("category_name", lambda s: s.mode().iat[0]))
    o = items.groupby("order_id", sort=False).agg(**agg).reset_index()
    o["shipping_delay_days"] = o["days_for_shipping_real"] - o["days_for_shipment_scheduled"]
    return o.sort_values("order_datetime").reset_index(drop=True)


def zone_daily_demand(orders: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    """Zone x calendar-day demand, ZERO-FILLED over the full date range.

    Zero-filling matters for forecasting: a day without orders is real zero
    demand, not a missing value.
    """
    d = orders[orders["in_demand_set"]]
    days = pd.date_range(d["order_date"].min(), d["order_date"].max(), freq="D")
    grid = pd.MultiIndex.from_product([zones["zone_id"], days], names=["zone_id", "date"])
    agg = (d.groupby(["zone_id", "order_date"])
             .agg(orders=("order_id", "size"), units=("units", "sum"), items=("n_items", "sum"),
                  sales=("sales", "sum"))
             .rename_axis(["zone_id", "date"]))
    out = agg.reindex(grid, fill_value=0).reset_index()
    out = out.merge(zones[["zone_id", "network"]], on="zone_id", how="left")
    brk = pd.Timestamp(load_config()["preprocessing"]["regime_break_date"])
    out["regime"] = np.where(out["date"] >= brk, "post_2017_10", "pre_2017_10")
    return out[["network", "zone_id", "date", "regime", "orders", "units", "items", "sales"]]


def network_category_daily(items: pd.DataFrame) -> pd.DataFrame:
    """Network x category x day units (not zero-filled), for category features."""
    d = items[items["in_demand_set"]]
    return (d.groupby(["network", "category_name", "order_date"])
             .agg(units=("order_item_quantity", "sum"), orders=("order_id", "nunique"), sales=("sales", "sum"))
             .reset_index().rename(columns={"order_date": "date"}))


# Step 9: validation
def reconcile(items: pd.DataFrame, orders: pd.DataFrame, zones: pd.DataFrame,
              zdaily: pd.DataFrame) -> pd.DataFrame:
    """Check that demand is conserved across aggregation levels, per network.

    Returns one row per (network, check) with the values compared and a pass flag.
    """
    cfg = load_config()
    diam = cfg["demand_zones"]["max_diameter_km"]
    di = items[items["in_demand_set"]]
    do = orders[orders["in_demand_set"]]
    rows = []

    def add(net, check, a, b, ok=None):
        ok = bool(np.isclose(a, b, rtol=0, atol=1e-6)) if ok is None else bool(ok)
        rows.append({"network": net, "check": check, "value_a": a, "value_b": b, "passed": ok})

    for net in sorted(di["network"].unique()):
        i, o = di[di["network"] == net], do[do["network"] == net]
        z, zd = zones[zones["network"] == net], zdaily[zdaily["network"] == net]
        add(net, "units: items == orders", i["order_item_quantity"].sum(), o["units"].sum())
        add(net, "units: orders == zone-day", o["units"].sum(), zd["units"].sum())
        add(net, "units: orders == zone table", o["units"].sum(), z["units"].sum())
        add(net, "orders: distinct item order_id == order rows", i["order_id"].nunique(), len(o))
        add(net, "orders: order rows == zone-day orders", len(o), zd["orders"].sum())
        add(net, "items: item rows == sum n_items", len(i), o["n_items"].sum())
        add(net, "sales: items == zone-day", round(i["sales"].sum(), 4), round(zd["sales"].sum(), 4))
        add(net, "every order has exactly one zone", int(o["zone_id"].isna().sum()), 0)
        add(net, "orders with >1 zone across items", int((i.groupby("order_id")["zone_id"].nunique() > 1).sum()), 0)
        add(net, "customers with >1 zone", int((i.groupby("customer_id")["zone_id"].nunique() > 1).sum()), 0)
        n_days = (do["order_date"].max() - do["order_date"].min()).days + 1
        add(net, "zone-day grid is complete (zones x days)", len(zd), len(z) * n_days)
        add(net, f"max zone radius <= diameter ({diam[net]} km)", round(z["max_km_from_centroid"].max(), 3),
            diam[net], ok=z["max_km_from_centroid"].max() <= diam[net] + 1e-6)
    add("ALL", "no item belongs to two networks", int((di.groupby("order_id")["network"].nunique() > 1).sum()), 0)
    return pd.DataFrame(rows)


def max_pairwise_diameter(items: pd.DataFrame) -> pd.DataFrame:
    """Exact max pairwise great-circle distance inside each zone (verifies complete linkage)."""
    u = items[items["in_demand_set"]][["network", "zone_id", "latitude", "longitude"]].drop_duplicates()
    out = []
    for zid, g in u.groupby("zone_id"):
        lat, lon = g["latitude"].to_numpy(), g["longitude"].to_numpy()
        if len(g) > 1:
            dm = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
            dmax = float(dm.max())
        else:
            dmax = 0.0
        out.append({"zone_id": zid, "network": g["network"].iat[0], "max_pairwise_km": dmax})
    return pd.DataFrame(out)


def coordinate_validation(items: pd.DataFrame) -> pd.DataFrame:
    """Evidence for interpreting Latitude/Longitude as the customer location.

    Compares the median coordinate of each reference city's customers with a
    public city-centre coordinate. Also reports the distance of each customer to
    their city median and the domestic-destination share per network.
    """
    cfg = load_config()
    c = items[items["coord_valid"]].drop_duplicates("customer_id")
    rows = []
    for ref in cfg["validation"]["reference_cities"]:
        g = c[(c["customer_state"] == ref["state"]) & (c["customer_city"] == ref["city"])]
        if g.empty:
            continue
        mlat, mlon = g["latitude"].median(), g["longitude"].median()
        dist = haversine_km(g["latitude"], g["longitude"], mlat, mlon)
        rows.append({"evidence": "reference city centre", "subject": f"{ref['city']}, {ref['state']}",
                     "n_customers": len(g), "data_median_lat": round(mlat, 4), "data_median_lon": round(mlon, 4),
                     "reference_lat": ref["lat"], "reference_lon": ref["lon"],
                     "km_median_to_reference": round(float(haversine_km(mlat, mlon, ref["lat"], ref["lon"])), 2),
                     "p50_km_customer_to_city_median": round(float(np.median(dist)), 2),
                     "p90_km_customer_to_city_median": round(float(np.percentile(dist, 90)), 2)})
    med = c.groupby(["customer_state", "customer_city"])[["latitude", "longitude"]].transform("median")
    c = c.assign(km=haversine_km(c["latitude"], c["longitude"], med["latitude"], med["longitude"]))
    for net, g in c[c["network"] != "Excluded"].groupby("network"):
        rows.append({"evidence": "customer to own-city median", "subject": net, "n_customers": len(g),
                     "p50_km_customer_to_city_median": round(float(g["km"].median()), 2),
                     "p90_km_customer_to_city_median": round(float(g["km"].quantile(0.9)), 2)})
    d = items[items["in_demand_set"]]
    for net, g in d.groupby("network"):
        rows.append({"evidence": "domestic destination share (orders)", "subject": net,
                     "n_customers": g["customer_id"].nunique(),
                     "value": round(float(g.drop_duplicates("order_id")["destination_domestic"].mean()), 4)})
    return pd.DataFrame(rows)


# Orchestration
@dataclass
class PreprocessResult:
    items: pd.DataFrame
    orders: pd.DataFrame
    zones: pd.DataFrame
    zone_daily: pd.DataFrame
    category_daily: pd.DataFrame
    quality_log: pd.DataFrame
    reconciliation: pd.DataFrame
    diameters: pd.DataFrame
    coord_validation: pd.DataFrame


CLEANED_COLUMNS_ORDER = [
    "order_item_id", "order_id", "customer_id", "order_datetime", "order_date", "shipping_datetime",
    "network", "zone_id", "latitude", "longitude", "customer_city", "customer_state", "customer_country",
    "customer_segment", "coord_region", "coord_valid", "coord_issue", "in_demand_set", "is_demand", "regime",
    "destination_domestic",
]


def run_preprocessing(write: bool = True) -> PreprocessResult:
    """Execute Phase 2 end to end and (optionally) persist every artefact."""
    clog = CleaningLog()
    raw = load_raw_orders(parse_dates=True, drop_pii=False)
    items = clean_items(raw, clog)
    del raw
    items, zones = assign_zones(items)
    for net, g in zones.groupby("network"):
        clog.add("demand zones", f"Cluster {net} coordinates into zones "
                 f"(complete linkage, diameter <= {load_config()['demand_zones']['max_diameter_km'][net]} km)",
                 "label zone_id", f"{len(g)} zones from {int(g['n_coordinates'].sum())} unique coordinates.",
                 records=int(items[items["network"].eq(net) & items["in_demand_set"]].shape[0]),
                 orders=int(g["n_orders"].sum()), units=int(g["units"].sum()))
    orders = aggregate_orders(items)
    zd = zone_daily_demand(orders, zones)
    cat = network_category_daily(items)
    rec = reconcile(items, orders, zones, zd)
    diam = max_pairwise_diameter(items)
    cval = coordinate_validation(items)
    clog.add("validation", "Aggregation reconciliation (items -> orders -> zone-day)",
             "assert", f"{int(rec['passed'].sum())}/{len(rec)} checks passed.")
    final = items["in_demand_set"]
    clog.add("final", "Spatial demand set", "result", "Rows used by forecasting and optimisation.",
             records=final.sum(), orders=items.loc[final, "order_id"].nunique(),
             units=items.loc[final, "order_item_quantity"].sum(), remaining_records=int(final.sum()),
             remaining_orders=int(items.loc[final, "order_id"].nunique()))
    qlog = clog.frame()

    cols = CLEANED_COLUMNS_ORDER + [c for c in items.columns if c not in CLEANED_COLUMNS_ORDER]
    items = items[cols]
    res = PreprocessResult(items, orders, zones, zd, cat, qlog, rec, diam, cval)
    if write:
        _write(res)
    if not rec["passed"].all():
        raise AssertionError("Aggregation reconciliation failed:\n" + rec[~rec["passed"]].to_string())
    return res


def _assert_no_pii(frame: pd.DataFrame, name: str) -> None:
    pii = {to_snake(c) for c in load_config()["dataset"]["pii_columns"]} | set(load_config()["dataset"]["pii_columns"])
    leaked = pii & set(frame.columns)
    if leaked:
        raise RuntimeError(f"PII columns {leaked} would be written to {name}")


def _write(r: PreprocessResult) -> None:
    proc, out = get_path("processed_dir"), get_path("outputs_dir")
    for frame, path in [(r.items, proc / "cleaned_data.csv"), (r.orders, proc / "orders.csv"),
                        (r.zones, proc / "demand_zones.csv"), (r.zone_daily, proc / "zone_daily_demand.csv"),
                        (r.category_daily, proc / "network_category_daily_demand.csv")]:
        _assert_no_pii(frame, path.name)
        frame.to_csv(path, index=False)
    r.quality_log.to_csv(out / "data_quality_report.csv", index=False)
    r.reconciliation.to_csv(out / "phase2_aggregation_reconciliation.csv", index=False)
    r.diameters.to_csv(out / "phase2_zone_diameters.csv", index=False)
    r.coord_validation.to_csv(out / "phase2_coordinate_validation.csv", index=False)
    r.zones.to_csv(out / "demand_zones.csv", index=False)  # small, committed copy
    log.info("Phase 2 artefacts written to %s and %s", proc, out)
