"""Phase 2 tests: zoning, demand definition, aggregation conservation, privacy.

Synthetic tests always run. Tests on the real processed outputs are skipped
when `python main.py preprocess` has not been run.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import get_path, load_config
from src.distance_calculator import haversine_matrix
from src.preprocessing import (CleaningLog, aggregate_orders, build_zones, reconcile, to_snake,
                               zone_daily_demand, zone_table)

PROC = get_path("processed_dir", create=False)
OUT = get_path("outputs_dir", create=False)
HAVE_REAL = (PROC / "cleaned_data.csv").exists()


# --------------------------------------------------------------------------- synthetic
def test_to_snake():
    assert to_snake("Days for shipping (real)") == "days_for_shipping_real"
    assert to_snake("Late_delivery_risk") == "late_delivery_risk"


@pytest.mark.parametrize("diam", [5.0, 25.0, 50.0])
def test_build_zones_respects_diameter(diam):
    rng = np.random.default_rng(0)
    pts = pd.DataFrame({"latitude": 40 + rng.normal(0, 0.6, 400), "longitude": -75 + rng.normal(0, 0.6, 400),
                        "weight": rng.integers(1, 10, 400)})
    z = build_zones(pts, diam, "T")
    for _, g in z.groupby("zone_id"):
        d = haversine_matrix(g.latitude, g.longitude, g.latitude, g.longitude)
        assert d.max() <= diam + 1e-6
    # IDs ranked by weight
    w = z.groupby("zone_id")["weight"].sum()
    assert w.idxmax() == "T-Z001"


def test_build_zones_deterministic_and_separates_far_points():
    pts = pd.DataFrame({"latitude": [40.0, 40.01, 34.0], "longitude": [-74.0, -74.01, -118.0], "weight": [1, 1, 5]})
    a, b = build_zones(pts, 50, "X"), build_zones(pts, 50, "X")
    assert a["zone_id"].tolist() == b["zone_id"].tolist()
    assert a.loc[0, "zone_id"] == a.loc[1, "zone_id"] != a.loc[2, "zone_id"]
    assert a.loc[2, "zone_id"] == "X-Z001"  # heaviest


def _synthetic_items() -> pd.DataFrame:
    """3 orders, 5 items, 2 zones; order 3 is cancelled (not in demand set)."""
    d = pd.DataFrame({
        "order_item_id": [1, 2, 3, 4, 5], "order_id": [10, 10, 11, 12, 12], "customer_id": [1, 1, 2, 3, 3],
        "order_item_quantity": [2, 3, 1, 4, 1], "sales": [20.0, 30.0, 5.0, 40.0, 10.0],
        "order_item_total": [18.0, 30.0, 5.0, 40.0, 9.0], "order_item_discount": [2.0, 0, 0, 0, 1.0],
        "order_profit_per_order": [1.0, 1, 1, 1, 1], "category_name": ["a", "b", "a", "a", "a"],
        "latitude": [40.0, 40.0, 34.0, 41.0, 41.0], "longitude": [-74.0, -74.0, -118.0, -73.0, -73.0],
        "network": ["CONUS"] * 5, "zone_id": ["US-Z001", "US-Z001", "US-Z002", "US-Z003", "US-Z003"],
        "order_datetime": pd.to_datetime(["2016-01-01 10:00"] * 2 + ["2016-01-02 09:00"] + ["2016-01-03 08:00"] * 2),
        "in_demand_set": [True, True, True, False, False], "regime": ["pre_2017_10"] * 5,
        "customer_city": ["A"] * 5, "customer_state": ["NY", "NY", "CA", "NY", "NY"],
    })
    d["order_date"] = d["order_datetime"].dt.normalize()
    d["shipping_datetime"] = d["order_datetime"] + pd.Timedelta(days=2)
    for c in ["customer_segment", "market", "order_region", "order_country", "shipping_mode", "order_status",
              "delivery_status", "type"]:
        d[c] = "x"
    d["destination_domestic"] = False
    d["late_delivery_risk"] = 0
    d["days_for_shipping_real"] = 2
    d["days_for_shipment_scheduled"] = 2
    d["is_demand"] = d["in_demand_set"]
    d["coord_valid"] = True
    return d


def test_order_aggregation_and_conservation():
    items = _synthetic_items()
    orders = aggregate_orders(items)
    assert len(orders) == 3
    o10 = orders.set_index("order_id").loc[10]
    assert o10["n_items"] == 2 and o10["units"] == 5 and o10["sales"] == 50.0
    zones = zone_table(items[items["in_demand_set"]])
    zd = zone_daily_demand(orders, zones)
    # cancelled order 12 must not appear anywhere in demand
    assert zd["units"].sum() == 6 and zd["orders"].sum() == 2
    assert set(zones["zone_id"]) == {"US-Z001", "US-Z002"}
    # zero-filled grid: 2 zones x 2 days (demand set spans 2016-01-01..02)
    assert len(zd) == 4 and (zd["orders"] == 0).sum() == 2
    rec = reconcile(items, orders, zones, zd)
    assert rec["passed"].all(), rec[~rec["passed"]]


def test_reconcile_detects_lost_units():
    items = _synthetic_items()
    orders = aggregate_orders(items)
    zones = zone_table(items[items["in_demand_set"]])
    zd = zone_daily_demand(orders, zones)
    zd.loc[0, "units"] += 1  # corrupt
    rec = reconcile(items, orders, zones, zd)
    assert not rec.set_index(["network", "check"]).loc[("CONUS", "units: orders == zone-day"), "passed"]


def test_cleaning_log_int_columns():
    log = CleaningLog()
    log.add("s", "r", "a", "why", records=3, remaining_records=3, remaining_orders=1)
    log.add("s", "r", "a", "why")
    f = log.frame()
    assert str(f["orders_remaining_in_demand_set"].dtype) == "Int64"


# --------------------------------------------------------------------------- real outputs
real = pytest.mark.skipif(not HAVE_REAL, reason="run `python main.py preprocess` first")


@real
def test_real_outputs_contain_no_pii():
    pii = set(load_config()["dataset"]["pii_columns"]) | {to_snake(c) for c in load_config()["dataset"]["pii_columns"]}
    pii |= {"customer_zipcode", "Customer Zipcode"}
    files = list(PROC.glob("*.csv")) + list(OUT.glob("*.csv"))
    assert files
    for f in files:
        cols = set(pd.read_csv(f, nrows=0).columns)
        assert not (cols & pii), f"{f.name} leaks {cols & pii}"


@real
def test_real_cleaned_data_keeps_every_raw_row():
    from src.data_loader import raw_file_path
    n_raw = sum(1 for _ in open(raw_file_path(), encoding="latin-1")) - 1
    n_clean = len(pd.read_csv(PROC / "cleaned_data.csv", usecols=["order_item_id"]))
    assert n_raw == n_clean


@real
def test_real_reconciliation_all_pass():
    rec = pd.read_csv(OUT / "phase2_aggregation_reconciliation.csv")
    assert rec["passed"].all()


@real
def test_real_zone_diameters_within_limits():
    d = pd.read_csv(OUT / "phase2_zone_diameters.csv")
    lim = load_config()["demand_zones"]["max_diameter_km"]
    assert (d["max_pairwise_km"] <= d["network"].map(lim) + 1e-6).all()


@real
def test_real_demand_set_excludes_cancelled_and_invalid_coords():
    c = pd.read_csv(PROC / "cleaned_data.csv",
                    usecols=["in_demand_set", "order_status", "coord_valid", "network", "zone_id"])
    d = c[c["in_demand_set"]]
    assert not d["order_status"].isin(["CANCELED", "SUSPECTED_FRAUD"]).any()
    assert d["coord_valid"].all() and d["zone_id"].notna().all()
    assert set(d["network"]) <= {"CONUS", "Puerto Rico", "Hawaii"}
    assert c.loc[~c["in_demand_set"], "zone_id"].isna().all()
