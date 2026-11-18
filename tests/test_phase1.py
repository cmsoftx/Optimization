"""Unit tests for Phase 1 (loading, distances, inspection logic).

They use small synthetic frames, so they run without the Kaggle file.
"""
from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd
import pytest

from src import data_inspection as di
from src.data_loader import REQUIRED_COLUMNS, extract_zip, validate_columns
from src.distance_calculator import haversine_km, haversine_matrix


def _frame() -> pd.DataFrame:
    """Two orders: order 1 has two items, order 2 has one item."""
    base = {c: ["x", "x", "x"] for c in REQUIRED_COLUMNS}
    df = pd.DataFrame(base)
    df["Order Id"] = [1, 1, 2]
    df["Order Item Id"] = [10, 11, 12]
    df["Customer Id"] = df["Order Customer Id"] = [100, 100, 200]
    df["order date (DateOrders)"] = pd.to_datetime(["2016-01-01 10:00"] * 2 + ["2016-01-02 09:00"])
    df["shipping date (DateOrders)"] = pd.to_datetime(["2016-01-03 10:00"] * 2 + ["2016-01-04 09:00"])
    df["Days for shipping (real)"] = [2, 2, 2]
    df["Order Item Quantity"] = [1, 3, 2]
    df["Order Item Product Price"] = [10.0, 20.0, 5.0]
    df["Sales"] = df["Order Item Product Price"] * df["Order Item Quantity"]
    df["Order Item Discount"] = [1.0, 0.0, 0.5]
    df["Order Item Total"] = df["Sales"] - df["Order Item Discount"]
    df["Sales per customer"] = df["Order Item Total"]
    df["Benefit per order"] = df["Order Profit Per Order"] = [1.0, -2.0, 3.0]
    df["Category Id"] = df["Product Category Id"] = [5, 6, 5]
    df["Order Item Cardprod Id"] = df["Product Card Id"] = [7, 8, 7]
    df["Latitude"] = [40.7, 40.7, 34.0]
    df["Longitude"] = [-74.0, -74.0, -118.2]
    df["Customer State"] = ["NY", "NY", "CA"]
    df["Customer Country"] = ["EE. UU."] * 3
    df["Order City"] = ["A", "A", "B"]
    df["Shipping Mode"] = ["Standard Class"] * 2 + ["First Class"]
    df["Order Status"] = ["COMPLETE"] * 3
    df["Category Name"] = ["c1", "c2", "c1"]
    return df


def test_haversine_known_distance():
    # New York -> Los Angeles is about 3,936 km great-circle.
    d = haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
    assert 3900 < float(d) < 3970


def test_haversine_zero_and_symmetry():
    m = haversine_matrix([40, 34], [-74, -118], [40, 34], [-74, -118])
    assert np.allclose(np.diag(m), 0.0)
    assert np.allclose(m, m.T)


def test_validate_columns_raises_on_missing():
    with pytest.raises(KeyError):
        validate_columns(pd.DataFrame({"Order Id": [1]}))


def test_integrity_checks_clean_frame_has_no_violations():
    res = di.integrity_checks(_frame()).set_index("check")
    must_be_zero = [c for c in res.index if not c.startswith("Negative profit")]
    assert (res.loc[must_be_zero, "violations"] == 0).all()
    assert res.loc["Negative profit (Order Profit Per Order < 0)", "violations"] == 1


def test_integrity_detects_order_level_inconsistency():
    df = _frame()
    df.loc[1, "Shipping Mode"] = "Same Day"  # same order, different mode
    res = di.integrity_checks(df).set_index("check")
    assert res.loc["Order Id with >1 distinct 'Shipping Mode'", "violations"] == 2


def test_aggregate_orders_one_row_per_delivery():
    orders = di.aggregate_orders(_frame()).set_index("Order Id")
    assert len(orders) == 2
    assert orders.loc[1, "n_items"] == 2 and orders.loc[1, "units"] == 4
    assert orders.loc[2, "units"] == 2


def test_coordinate_checks_flag_sign_error():
    df = _frame()
    df.loc[2, "Longitude"] = 118.2  # flipped sign
    summary, flagged = di.coordinate_checks(df)
    s = summary.set_index("check")
    assert s.loc["positive_longitude", "records"] == 1
    assert s.loc["outside_us_boxes", "records"] == 1
    assert len(flagged) == 1


def test_column_profile_redacts_pii():
    df = _frame().assign(**{"Customer Fname": ["Ann", "Ann", "Bob"]})
    prof = di.column_profile(df).set_index("column")
    assert prof.loc["Customer Fname", "example"] == "<redacted PII>"
    assert bool(prof.loc["Customer Fname", "is_pii"])


def test_extract_zip_ignores_unexpected_and_traversal(tmp_path):
    zp = tmp_path / "a.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("DataCoSupplyChainDataset.csv", "a,b\n1,2\n")
        zf.writestr("../../evil.py", "print('x')")
        zf.writestr("nested/DescriptionDataCoSupplyChain.csv", "FIELDS,DESCRIPTION\n")
    out = tmp_path / "raw"
    files = extract_zip(zp, out)
    names = sorted(p.name for p in files)
    assert names == ["DataCoSupplyChainDataset.csv", "DescriptionDataCoSupplyChain.csv"]
    assert not (tmp_path / "evil.py").exists()
    assert all(p.parent == out for p in files)
