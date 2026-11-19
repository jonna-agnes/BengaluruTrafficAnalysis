"""Smoke test: the Streamlit app runs end to end and renders its dashboard."""
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parent.parent / "streamlit_app" / "app.py"
TOTAL_WINDOWS = len(pd.read_parquet(APP.parent / "data" / "traffic_5min.parquet"))


def test_app_renders_without_errors():
    at = AppTest.from_file(str(APP), default_timeout=120).run()

    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value.endswith("Bengaluru Traffic Intelligence")

    metrics = {m.label: m.value for m in at.metric}
    assert metrics["5-min windows"] == f"{TOTAL_WINDOWS:,}"
    assert "Model accuracy" in metrics


def test_area_filter_updates_dashboard():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.multiselect[0].set_value(["Silk Board"]).run()

    assert not at.exception, [e.value for e in at.exception]
    windows = int(next(m.value for m in at.metric if m.label == "5-min windows").replace(",", ""))
    assert 0 < windows < TOTAL_WINDOWS
