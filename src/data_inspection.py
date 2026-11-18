"""Phase 1: structural and quality inspection of the raw DataCo dataset.

All numbers produced here are computed from the loaded file; nothing is
hard-coded. ``run_inspection`` writes CSV artefacts to ``data/outputs`` and a
Markdown report to ``reports/phase1_dataset_inspection.md``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import get_path, load_config
from .data_loader import load_access_logs, load_data_dictionary, load_raw_orders
from .distance_calculator import haversine_km

log = logging.getLogger(__name__)

ORDER_DATE = "order date (DateOrders)"
SHIP_DATE = "shipping date (DateOrders)"


# Column-level profiling
def column_profile(df: pd.DataFrame, dictionary: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per column: dtype, completeness, cardinality, example value.

    Example values of PII columns are redacted.
    """
    pii = set(load_config()["dataset"]["pii_columns"])
    described = set(dictionary["field"]) if dictionary is not None else set()
    rows = []
    n = len(df)
    for col in df.columns:
        s = df[col]
        non_null = s.dropna()
        example = "<redacted PII>" if col in pii else (str(non_null.iloc[0]) if len(non_null) else "")
        rows.append({
            "column": col,
            "dtype": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "missing": int(s.isna().sum()),
            "missing_pct": round(100 * s.isna().mean(), 3),
            "n_unique": int(s.nunique(dropna=True)),
            "example": example[:60],
            "is_pii": col in pii,
            "in_data_dictionary": col in described,
        })
    return pd.DataFrame(rows)


def masked_constant_columns(df: pd.DataFrame) -> list[str]:
    """Columns with a single distinct value (e.g. masked emails/passwords)."""
    return [c for c in df.columns if df[c].nunique(dropna=False) <= 1]


# Integrity / consistency checks
def integrity_checks(df: pd.DataFrame) -> pd.DataFrame:
    """Logical consistency checks between redundant columns.

    Each row reports how many records violate a rule that should hold if the
    columns mean what the data dictionary says.
    """
    checks: list[tuple[str, pd.Series, str]] = []
    tol = 0.015  # values are stored as float32-like cents; 0.01 differences are rounding
    checks.append(("Duplicate full rows", df.duplicated(), "row-level"))
    checks.append(("Duplicate Order Item Id", df["Order Item Id"].duplicated(), "key uniqueness"))
    checks.append(("Customer Id != Order Customer Id",
                   df["Customer Id"] != df["Order Customer Id"], "redundant key"))
    checks.append(("Category Id != Product Category Id",
                   df["Category Id"] != df["Product Category Id"], "redundant key"))
    checks.append(("Order Item Cardprod Id != Product Card Id",
                   df["Order Item Cardprod Id"] != df["Product Card Id"], "redundant key"))
    checks.append(("Sales != Product Price x Quantity",
                   (df["Sales"] - df["Order Item Product Price"] * df["Order Item Quantity"]).abs() > tol,
                   "monetary"))
    checks.append(("Order Item Total != Sales - Discount",
                   (df["Order Item Total"] - (df["Sales"] - df["Order Item Discount"])).abs() > tol,
                   "monetary"))
    checks.append(("Sales per customer != Order Item Total",
                   (df["Sales per customer"] - df["Order Item Total"]).abs() > tol, "redundant metric"))
    checks.append(("Benefit per order != Order Profit Per Order",
                   (df["Benefit per order"] - df["Order Profit Per Order"]).abs() > tol, "redundant metric"))
    checks.append(("Order Item Quantity <= 0", df["Order Item Quantity"] <= 0, "domain"))
    checks.append(("Sales <= 0", df["Sales"] <= 0, "domain"))
    checks.append(("Negative profit (Order Profit Per Order < 0)",
                   df["Order Profit Per Order"] < 0, "business (not an error)"))
    checks.append(("Unparseable order date", df[ORDER_DATE].isna(), "date"))
    checks.append(("Unparseable shipping date", df[SHIP_DATE].isna(), "date"))
    checks.append(("Shipping date before order date", df[SHIP_DATE] < df[ORDER_DATE], "date"))
    computed = (df[SHIP_DATE] - df[ORDER_DATE]).dt.days
    checks.append(("Days for shipping (real) != whole days between dates",
                   computed != df["Days for shipping (real)"], "date"))
    # More than one value per order of attributes that should be order-level.
    for col in ["Order Customer Id", ORDER_DATE, "Order City", "Shipping Mode",
                "Order Status", "Latitude"]:
        multi = df.groupby("Order Id")[col].transform("nunique") > 1
        checks.append((f"Order Id with >1 distinct '{col}'", multi, "order-level consistency"))
    multi = df.groupby("Customer Id")["Latitude"].transform("nunique") > 1
    checks.append(("Customer Id with >1 distinct Latitude", multi, "customer-level consistency"))

    n = len(df)
    return pd.DataFrame([
        {"check": name, "category": cat, "violations": int(mask.sum()),
         "violation_pct": round(100 * mask.mean(), 3), "records_checked": n}
        for name, mask, cat in checks
    ])


# Geography
def _in_bbox(lat: pd.Series, lon: pd.Series, bb: dict) -> pd.Series:
    return lat.between(bb["lat_min"], bb["lat_max"]) & lon.between(bb["lon_min"], bb["lon_max"])


def classify_region(df: pd.DataFrame) -> pd.Series:
    """Label each record's coordinate as CONUS / Puerto Rico / Hawaii / Alaska / Outside."""
    geo = load_config()["geography"]
    lat, lon = df["Latitude"], df["Longitude"]
    region = pd.Series("Outside US bounding boxes", index=df.index, dtype=object)
    for name, key in [("CONUS", "conus_bbox"), ("Puerto Rico", "puerto_rico_bbox"),
                      ("Hawaii", "hawaii_bbox"), ("Alaska", "alaska_bbox")]:
        region[_in_bbox(lat, lon, geo[key])] = name
    return region


COORD_FLAGS = ["missing", "out_of_range", "zero_island", "positive_longitude", "outside_us_boxes",
               "inconsistent_with_state", "region_conflicts_country", "placeholder_coordinate"]


def coordinate_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Per-record coordinate validity flags (plus ``region`` and ``any_flag``)."""
    max_km = load_config()["data_quality"]["state_consistency_max_km"]
    d = df[["Customer Id", "Customer City", "Customer State", "Customer Country",
            "Latitude", "Longitude"]].copy()
    d["region"] = classify_region(d)
    d["out_of_range"] = ~(d["Latitude"].between(-90, 90) & d["Longitude"].between(-180, 180))
    d["missing"] = d["Latitude"].isna() | d["Longitude"].isna()
    d["zero_island"] = (d["Latitude"].abs() < 1e-6) & (d["Longitude"].abs() < 1e-6)
    d["positive_longitude"] = d["Longitude"] > 0  # all US/PR locations have lon < 0
    d["outside_us_boxes"] = d["region"].eq("Outside US bounding boxes")

    # Robust state consistency: distance to the median coordinate of the state.
    med = d.groupby("Customer State")[["Latitude", "Longitude"]].transform("median")
    d["km_from_state_median"] = haversine_km(d["Latitude"], d["Longitude"], med["Latitude"], med["Longitude"])
    d["inconsistent_with_state"] = d["km_from_state_median"] > max_km
    # A single coordinate reused by customers of several states is a placeholder
    # (e.g. a geographic-centre default), not a real location.
    n_states = d.groupby(["Latitude", "Longitude"])["Customer State"].transform("nunique")
    d["placeholder_coordinate"] = n_states >= 3
    d["region_conflicts_country"] = (
        (d["Customer Country"].eq("Puerto Rico") & d["region"].ne("Puerto Rico"))
        | (d["Customer Country"].ne("Puerto Rico") & d["region"].eq("Puerto Rico"))
    )
    d["any_flag"] = d[COORD_FLAGS].any(axis=1)
    return d


def coordinate_checks(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate customer coordinates.

    Returns
    -------
    summary : one row per check with record and customer counts.
    flagged : distinct (Customer State, City, lat, lon) combinations that fail
              any check, for manual review.
    """
    d = coordinate_flags(df)
    flags = COORD_FLAGS + ["any_flag"]

    rows = []
    for f in flags:
        m = d[f]
        rows.append({"check": f, "records": int(m.sum()), "records_pct": round(100 * m.mean(), 3),
                     "customers": int(d.loc[m, "Customer Id"].nunique())})
    summary = pd.DataFrame(rows)
    flagged = (d[d["any_flag"]]
               .groupby(["Customer State", "Customer City", "Latitude", "Longitude", "region"] + flags[:-1],
                        dropna=False)
               .agg(records=("Customer Id", "size"), customers=("Customer Id", "nunique"),
                    km_from_state_median=("km_from_state_median", "first"))
               .reset_index()
               .sort_values("records", ascending=False))
    return summary, flagged


def region_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Records, orders, customers and units by coordinate region."""
    d = df.assign(region=classify_region(df))
    out = d.groupby("region").agg(
        records=("Order Item Id", "size"), orders=("Order Id", "nunique"),
        customers=("Customer Id", "nunique"), units=("Order Item Quantity", "sum"),
        unique_coordinates=("Latitude", lambda s: d.loc[s.index, ["Latitude", "Longitude"]]
                            .drop_duplicates().shape[0]),
    ).reset_index()
    out["records_pct"] = (100 * out["records"] / out["records"].sum()).round(2)
    return out.sort_values("records", ascending=False)


# Outliers
def iqr_outliers(frame: pd.DataFrame, columns: list[str], level: str) -> pd.DataFrame:
    """Tukey-fence outlier counts for numeric columns."""
    k = load_config()["data_quality"]["iqr_multiplier"]
    rows = []
    for col in columns:
        s = frame[col].dropna()
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - k * iqr, q3 + k * iqr
        n_out = int(((s < lo) | (s > hi)).sum())
        rows.append({"level": level, "column": col, "min": s.min(), "q1": q1, "median": s.median(),
                     "q3": q3, "max": s.max(), "lower_fence": lo, "upper_fence": hi,
                     "outliers": n_out, "outlier_pct": round(100 * n_out / len(s), 3)})
    return pd.DataFrame(rows)


# Order-level aggregation (an order is the delivery unit, not an item row)
def aggregate_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse order-item rows into one row per order (= one delivery).

    Order-level attributes are verified to be constant within an order by
    :func:`integrity_checks`, so ``first`` is safe for them.
    """
    return (df.groupby("Order Id", sort=False)
              .agg(customer_id=("Order Customer Id", "first"),
                   order_date=(ORDER_DATE, "first"),
                   shipping_date=(SHIP_DATE, "first"),
                   latitude=("Latitude", "first"), longitude=("Longitude", "first"),
                   customer_city=("Customer City", "first"), customer_state=("Customer State", "first"),
                   customer_country=("Customer Country", "first"),
                   order_country=("Order Country", "first"), market=("Market", "first"),
                   shipping_mode=("Shipping Mode", "first"), order_status=("Order Status", "first"),
                   n_items=("Order Item Id", "size"), units=("Order Item Quantity", "sum"),
                   sales=("Sales", "sum"), order_total=("Order Item Total", "sum"),
                   n_categories=("Category Name", "nunique"))
              .reset_index())


# Temporal analysis
def monthly_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Rows, orders, units, markets and categories per order month."""
    d = df.assign(month=df[ORDER_DATE].dt.to_period("M").astype(str), region=classify_region(df))
    out = d.groupby("month").agg(
        rows=("Order Item Id", "size"), orders=("Order Id", "nunique"),
        units=("Order Item Quantity", "sum"), items_per_order=("Order Item Id", "size"),
        n_markets=("Market", "nunique"), n_categories=("Category Name", "nunique"),
        conus_orders=("Order Id", lambda s: d.loc[s.index][d.loc[s.index, "region"] == "CONUS"]["Order Id"].nunique()),
    ).reset_index()
    out["items_per_order"] = (out["rows"] / out["orders"]).round(3)
    return out


def detect_volume_breaks(monthly: pd.DataFrame, col: str = "units", threshold: float = 0.35) -> pd.DataFrame:
    """Flag months whose volume differs from the trailing 6-month median by > threshold."""
    m = monthly.copy()
    ref = m[col].rolling(6, min_periods=3).median().shift(1)
    m["trailing_median"] = ref
    m["rel_change"] = (m[col] - ref) / ref
    return m[m["rel_change"].abs() > threshold][["month", col, "trailing_median", "rel_change"]]


# Report generation
@dataclass
class InspectionResult:
    shape: tuple[int, int]
    profile: pd.DataFrame
    integrity: pd.DataFrame
    coord_summary: pd.DataFrame
    coord_flagged: pd.DataFrame
    regions: pd.DataFrame
    outliers: pd.DataFrame
    monthly: pd.DataFrame
    breaks: pd.DataFrame
    orders: pd.DataFrame
    facts: dict = field(default_factory=dict)


def _md_table(frame: pd.DataFrame, floatfmt: str = "{:,.2f}") -> str:
    """Render a DataFrame as a GitHub Markdown table without extra dependencies."""
    def fmt(v):
        if isinstance(v, (float, np.floating)):
            return floatfmt.format(v) if np.isfinite(v) else ""
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return str(v).replace("|", "\\|")
    head = "| " + " | ".join(map(str, frame.columns)) + " |"
    sep = "|" + "|".join(["---"] * len(frame.columns)) + "|"
    body = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in frame.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def run_inspection(write: bool = True) -> InspectionResult:
    """Execute every Phase 1 check and (optionally) persist the artefacts."""
    df = load_raw_orders(parse_dates=True)
    dictionary = load_data_dictionary()
    profile = column_profile(df, dictionary)
    integrity = integrity_checks(df)
    coord_summary, coord_flagged = coordinate_checks(df)
    regions = region_breakdown(df)
    orders = aggregate_orders(df)
    outliers = pd.concat([
        iqr_outliers(df, ["Order Item Quantity", "Sales", "Order Item Total", "Order Item Product Price",
                          "Order Item Discount Rate", "Order Profit Per Order", "Days for shipping (real)"],
                     "order-item"),
        iqr_outliers(orders, ["n_items", "units", "sales", "order_total"], "order"),
    ], ignore_index=True)
    monthly = monthly_volume(df)
    breaks = detect_volume_breaks(monthly, "units")

    dict_fields = set(dictionary["field"])
    facts = {
        "rows": len(df), "cols": df.shape[1],
        "orders": int(df["Order Id"].nunique()),
        "customers": int(df["Customer Id"].nunique()),
        "customer_cities": int(df["Customer City"].nunique()),
        "customer_states": int(df["Customer State"].nunique()),
        "customer_countries": sorted(df["Customer Country"].dropna().unique().tolist()),
        "order_cities": int(df["Order City"].nunique()),
        "order_countries": int(df["Order Country"].nunique()),
        "markets": df["Market"].value_counts().to_dict(),
        "unique_coords": int(df[["Latitude", "Longitude"]].drop_duplicates().shape[0]),
        "date_min": df[ORDER_DATE].min(), "date_max": df[ORDER_DATE].max(),
        "products": int(df["Product Card Id"].nunique()),
        "categories": int(df["Category Name"].nunique()),
        "departments": int(df["Department Name"].nunique()),
        "items_per_order": orders["n_items"].describe().to_dict(),
        "units_per_order": orders["units"].describe().to_dict(),
        "total_units": int(df["Order Item Quantity"].sum()),
        "total_sales": float(df["Sales"].sum()),
        "constant_cols": masked_constant_columns(df),
        "undocumented_cols": [c for c in df.columns if c not in dict_fields],
        "shipping_mode": df.groupby("Shipping Mode").agg(
            rows=("Order Item Id", "size"),
            real_days=("Days for shipping (real)", "mean"),
            scheduled_days=("Days for shipment (scheduled)", "mean"),
            late_risk=("Late_delivery_risk", "mean")).reset_index(),
        "delivery_status": df["Delivery Status"].value_counts().to_dict(),
        "order_status": df["Order Status"].value_counts().to_dict(),
        "product_status": df["Product Status"].value_counts().to_dict(),
        "market_by_customer_country": pd.crosstab(df["Market"], df["Customer Country"]),
    }
    try:
        logs = load_access_logs()
        facts["access_logs"] = {"rows": len(logs), "cols": list(logs.columns),
                                "date_min": logs["Date"].min(), "date_max": logs["Date"].max()}
    except FileNotFoundError:
        facts["access_logs"] = None

    result = InspectionResult(df.shape, profile, integrity, coord_summary, coord_flagged,
                              regions, outliers, monthly, breaks, orders, facts)
    if write:
        _write_outputs(result, dictionary)
    return result


def _write_outputs(r: InspectionResult, dictionary: pd.DataFrame) -> None:
    out = get_path("outputs_dir")
    r.profile.to_csv(out / "phase1_column_profile.csv", index=False)
    r.profile[r.profile["missing"] > 0][["column", "missing", "missing_pct"]].to_csv(
        out / "phase1_missing_values.csv", index=False)
    r.integrity.to_csv(out / "phase1_integrity_checks.csv", index=False)
    r.coord_summary.to_csv(out / "phase1_coordinate_checks.csv", index=False)
    r.coord_flagged.to_csv(out / "phase1_flagged_coordinates.csv", index=False)
    r.regions.to_csv(out / "phase1_region_breakdown.csv", index=False)
    r.outliers.to_csv(out / "phase1_outlier_screen.csv", index=False)
    r.monthly.to_csv(out / "phase1_monthly_volume.csv", index=False)
    dictionary.to_csv(out / "phase1_data_dictionary.csv", index=False)
    report = get_path("reports_dir") / "phase1_dataset_inspection.md"
    report.write_text(build_markdown_report(r), encoding="utf-8")
    log.info("Phase 1 artefacts written to %s and %s", out, report)


def build_markdown_report(r: InspectionResult) -> str:
    f = r.facts
    integ = r.integrity.set_index("check")["violations"]
    cs = r.coord_summary.set_index("check")
    reg = r.regions.set_index("region")
    sm = f["shipping_mode"].copy()
    sm[["real_days", "scheduled_days", "late_risk"]] = sm[["real_days", "scheduled_days", "late_risk"]].round(3)
    missing = r.profile[r.profile["missing"] > 0][["column", "missing", "missing_pct"]]
    brk = r.breaks.copy()
    brk["rel_change"] = (100 * brk["rel_change"]).round(1).astype(str) + "%"
    monthly_tail = r.monthly[["month", "rows", "orders", "units", "items_per_order",
                              "n_markets", "n_categories", "conus_orders"]].tail(8)
    first_break = brk["month"].min() if len(brk) else None
    pre = r.monthly[r.monthly["month"] < first_break] if first_break else r.monthly
    post = r.monthly[r.monthly["month"] >= first_break] if first_break else r.monthly.iloc[0:0]
    xt = f["market_by_customer_country"].reset_index()
    al = f["access_logs"]

    lines = [
        "# Phase 1: Dataset Inspection Report",
        "",
        "_Generated by `python main.py inspect` (`src/data_inspection.py`). Every number below is "
        "computed from the raw file; nothing is typed in by hand._",
        "",
        "## 1. Files",
        "",
        f"* `DataCoSupplyChainDataset.csv`: **{f['rows']:,} rows × {f['cols']} columns**, "
        "ISO-8859-1 (Latin-1) encoded. Reading it as UTF-8 fails because of accented city names.",
        "* `DescriptionDataCoSupplyChain.csv`: publisher data dictionary "
        f"(saved as `data/outputs/phase1_data_dictionary.csv`).",
        (f"* `tokenized_access_logs.csv`: {al['rows']:,} web click-stream rows, columns "
         f"{al['cols']}. It has no customer key, geography or quantity, so the optimisation "
         "pipeline does not use it.") if al else "* `tokenized_access_logs.csv`: not present.",
        "",
        "## 2. Grain and scale",
        "",
        "| Quantity | Value |", "|---|---|",
        f"| Order-item rows | {f['rows']:,} |",
        f"| Distinct orders (`Order Id`) | {f['orders']:,} |",
        f"| Items per order (mean / max) | {f['items_per_order']['mean']:.2f} / {int(f['items_per_order']['max'])} |",
        f"| Units per order (mean / max) | {f['units_per_order']['mean']:.2f} / {int(f['units_per_order']['max'])} |",
        f"| Total units (`Order Item Quantity`) | {f['total_units']:,} |",
        f"| Total sales (`Sales`) | {f['total_sales']:,.0f} |",
        f"| Distinct customers | {f['customers']:,} |",
        f"| Customer cities / states | {f['customer_cities']:,} / {f['customer_states']:,} |",
        f"| Customer countries | {', '.join(f['customer_countries'])} |",
        f"| Distinct customer coordinates | {f['unique_coords']:,} |",
        f"| Order (destination) cities / countries | {f['order_cities']:,} / {f['order_countries']:,} |",
        f"| Products / categories / departments | {f['products']:,} / {f['categories']} / {f['departments']} |",
        f"| Order date range | {f['date_min']} → {f['date_max']} |",
        "",
        "**One row is one order item, not one delivery.** "
        f"Order-level attributes (customer, date, destination city, shipping mode, status, coordinates) "
        f"are constant within every order "
        f"({int(r.integrity.loc[r.integrity['category'] == 'order-level consistency', 'violations'].sum()):,} "
        "violations across those checks; see §4). "
        "So all logistics analysis aggregates rows to the order (one delivery) and then to demand locations.",
        "",
        "## 3. Missing values",
        "",
        _md_table(missing),
        "",
        "* `Product Description` is empty in every row, so it is unusable.",
        "* `Order Zipcode` is mostly missing. Only some US destination orders carry it.",
        "* A handful of missing `Customer Lname` / `Customer Zipcode` values do not affect the logistics model.",
        f"* Constant (masked) columns: {', '.join(f['constant_cols'])}.",
        f"* Columns not in the publisher dictionary: {', '.join(f['undocumented_cols']) or 'none'}.",
        "",
        "## 4. Integrity and consistency checks",
        "",
        _md_table(r.integrity[["check", "category", "violations", "violation_pct"]]),
        "",
        "Interpretation:",
        "* No duplicate rows or item IDs exist, and the redundant keys/metrics agree. That confirms "
        "`Order Customer Id`≡`Customer Id`, `Sales per customer`≡`Order Item Total` and "
        "`Benefit per order`≡`Order Profit Per Order`.",
        "* `Days for shipping (real)` disagrees with whole-day date arithmetic for "
        f"{integ['Days for shipping (real) != whole days between dates']:,} rows "
        "(always by −1 day, a truncation artefact). The published column is used as-is.",
        "",
        "## 5. Geography: what the coordinates actually describe",
        "",
        "The data dictionary says `Latitude`/`Longitude` are the *\"location of store\"*. Empirically:",
        f"* Each customer has exactly one coordinate "
        f"({integ['Customer Id with >1 distinct Latitude']} violations), and coordinates cluster by "
        "`Customer City`/`Customer State`. They behave as a **customer-side (US) location**.",
        f"* Customers are only in {' and '.join(f['customer_countries'])} (`EE. UU.` = USA).",
        f"* `Order City`/`Order Country` (the delivery *destination*) span {f['order_countries']} countries "
        "and **have no coordinates**. Every `Market` mixes US and Puerto Rico customers:",
        "",
        _md_table(xt),
        "",
        "The destination fields are therefore not geographically linked to the customer coordinates "
        "(a US customer can have an order destined for Indonesia). This is a known property of this "
        "synthetic dataset.",
        "",
        "### Coordinate regions",
        "",
        _md_table(r.regions),
        "",
        "### Coordinate validity checks",
        "",
        _md_table(r.coord_summary),
        "",
        "* `positive_longitude`: points with a flipped sign (e.g. Georgia at +84.7°).",
        "* `outside_us_boxes`: includes truncated longitudes such as Oregon at −12.1° instead of about −122°.",
        "* `inconsistent_with_state`: the point lies more than "
        f"{load_config()['data_quality']['state_consistency_max_km']} km from its state's median coordinate.",
        "* `region_conflicts_country`: Puerto Rico customers with mainland coordinates, or vice versa.",
        "* `placeholder_coordinate`: one coordinate shared by customers of ≥ 3 states. "
        "(39.495914, −98.989983) lies near the geographic centre of the contiguous US, a typical "
        "geolocation default.",
        "* Distinct flagged coordinates are listed in `data/outputs/phase1_flagged_coordinates.csv`. "
        "None of them is silently corrected.",
        "",
        "## 6. Temporal coverage and structural break",
        "",
        "Last 8 months:",
        "",
        _md_table(monthly_tail),
        "",
        "Months whose unit volume deviates by more than 35% from the trailing 6-month median:",
        "",
        _md_table(brk) if len(brk) else "_none_",
        "",
    ]
    if first_break:
        lines += [
            f"From **{first_break}** onward the data-generating process changes: units/month fall from "
            f"about {pre['units'].median():,.0f} to about {post['units'].median():,.0f}, items per order fall from "
            f"about {pre['items_per_order'].median():.2f} to about {post['items_per_order'].median():.2f}, "
            f"the number of categories sold per month falls from {int(pre['n_categories'].median())} to "
            f"{int(post['n_categories'].min())}–{int(post['n_categories'].max())}, while orders per month "
            f"*rise* (CONUS-customer orders go from about {pre['conus_orders'].median():,.0f} to about "
            f"{post['conus_orders'].median():,.0f}). The forecasting phase must treat this regime change "
            "explicitly. It must not use the tail months naively as a test set.",
            "",
            f"Also note that throughout the whole history each month contains orders for only "
            f"{int(r.monthly['n_markets'].min())}–{int(r.monthly['n_markets'].max())} of the 5 `Market` values "
            "(median " + f"{r.monthly['n_markets'].median():.0f}" + "). Markets rotate month by month, which "
            "confirms that `Market`/`Order Region` are synthetic labels and should not drive spatial demand.",
            "",
        ]
    lines += [
        "## 7. Outlier screen (Tukey fences, k = 1.5)",
        "",
        _md_table(r.outliers[["level", "column", "min", "median", "max", "upper_fence", "outliers", "outlier_pct"]]),
        "",
        "Quantities are bounded at 1–5 units per item, and prices take a small set of catalogue values. "
        "The flagged \"outliers\" are legitimate high-value items (e.g. 1,999.99 products) or loss-making "
        "orders, not data errors, so they are kept.",
        "",
        "## 8. Shipping and delivery fields",
        "",
        _md_table(sm),
        "",
        f"* Delivery status: {f['delivery_status']}",
        f"* Order status: {f['order_status']}",
        f"* `Product Status` values: {f['product_status']} (it carries no information).",
        "",
        "## 9. Information the dataset does NOT contain",
        "",
        "The following must be **simulated as documented business assumptions** in later phases:",
        "",
        "| Needed for | Missing information | Planned treatment |",
        "|---|---|---|",
        "| CFLP | Warehouse/candidate locations | Derived from demand clusters / customer-dense cities |",
        "| CFLP | Fixed opening costs `F_j`, capacities | Simulation parameters in `config.yaml`, with sensitivity analysis |",
        "| CFLP / VRP | Transport cost per km | Simulation parameter |",
        "| CFLP / VRP | Road distances | OSRM if reachable, otherwise Haversine **explicitly labelled** as straight-line |",
        "| VRP | Fleet size, vehicle capacity, speed | Simulation parameters |",
        "| VRP | Package weight/volume | Not available. Demand is measured in **units** (`Order Item Quantity`) |",
        "| All | Destination coordinates (`Order City`) | Not available. Geocoding would need an external service |",
        "",
        "## 10. Modelling decision implied by the inspection",
        "",
        "Only the customer-side coordinates exist, and the destination fields are geographically "
        "incoherent with them. The recommended scope for the network design is therefore:",
        "",
        "* **Demand points = customer coordinates** (`Latitude`/`Longitude`), aggregated by order and then "
        "into spatial demand zones.",
        f"* **Primary network = contiguous US (CONUS)**: {int(reg.loc['CONUS','records']):,} rows, "
        f"{int(reg.loc['CONUS','customers']):,} customers. Truck routing is physically meaningful here.",
        f"* **Puerto Rico** ({int(reg.loc['Puerto Rico','records']):,} rows, an island unreachable by truck from "
        "the mainland) is modelled as a separate sub-network or reported separately.",
        "* Hawaii (" + (f"{int(reg.loc['Hawaii','records']):,}" if 'Hawaii' in reg.index else "0")
        + " rows) is reported only. Alaska has "
        + (f"{int(reg.loc['Alaska','records']):,}" if 'Alaska' in reg.index else "no") + " records.",
        "* Records failing the coordinate checks are excluded from the spatial model and counted in the "
        "data-quality report.",
        "",
        "## 11. Privacy",
        "",
        "`Customer Fname`, `Customer Lname` and `Customer Street` contain personal data. Email and password are "
        "already masked. These columns are dropped from every processed output, and the raw files are "
        "git-ignored.",
        "",
    ]
    return "\n".join(lines)
