"""Dashboard smoke tests: every page renders without exceptions; the what-if page really re-optimises."""
from __future__ import annotations

import pytest

from src.config import PROJECT_ROOT

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "dashboard" / "app.py")
OUT = PROJECT_ROOT / "data" / "outputs"
pytestmark = pytest.mark.skipif(not (OUT / "final_performance_summary.csv").exists(), reason="run the pipeline first")
PAGES = ["Executive overview", "Data analytics", "Demand forecasting", "Warehouse optimisation", "Delivery routing",
         "Algorithm performance", "What-if simulation", "Reports & downloads"]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, [e.value for e in at.exception]


def test_what_if_runs_real_optimisation_for_puerto_rico():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    at.sidebar.radio[0].set_value("What-if simulation").run()
    at.radio[0].set_value("Puerto Rico").run()
    at.button[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [m.label for m in at.metric]
    assert "Warehouses" in labels and "Total cost / wk" in labels
    assert at.success or at.error  # feasibility verdict is shown
