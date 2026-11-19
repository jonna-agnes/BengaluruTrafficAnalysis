"""Smoke tests: the Streamlit app runs end to end and every tab works for its use case."""
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parent.parent / "streamlit_app" / "app.py"
TOTAL_WINDOWS = len(pd.read_parquet(APP.parent / "data" / "traffic_5min.parquet"))


def run_app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def metric(at: AppTest, label: str) -> str:
    return next(m.value for m in at.metric if m.label == label)


def test_overview_shows_all_data_by_default():
    at = run_app()
    assert at.title[0].value.endswith("Bengaluru Traffic Intelligence")
    assert metric(at, "5-min windows") == f"{TOTAL_WINDOWS:,}"     # empty area filter = all areas


def test_area_filter_narrows_the_dashboard():
    at = run_app()
    at.sidebar.multiselect[0].set_value(["Silk Board"]).run()
    assert not at.exception
    assert 0 < int(metric(at, "5-min windows").replace(",", "")) < TOTAL_WINDOWS


def test_filter_with_no_data_shows_a_message_not_an_error():
    at = run_app()
    days = pd.read_parquet(APP.parent / "data" / "traffic_5min.parquet", columns=["date_day", "is_weekend"])
    weekday = days.loc[~days["is_weekend"], "date_day"].min()
    at.sidebar.select_slider[0].set_value((weekday, weekday))
    at.sidebar.radio[0].set_value("Weekends").run()
    assert not at.exception
    assert any("No data for these filters" in i.value for i in at.info)
    assert any(m.label == "Roads High/Severe in 30 min" for m in at.metric)   # forecast tab still works


def test_forecast_tab_raises_alerts():
    at = run_app()
    high, total = metric(at, "Roads High/Severe in 30 min").split(" of ")
    assert int(total) == 20 and 0 <= int(high) <= 20
    assert metric(at, "Model accuracy").endswith("%")


def test_trip_planner_recommends_best_and_worst_times():
    at = run_app()
    assert any("Best time" in s.value for s in at.success)
    assert any("Avoid" in e.value for e in at.error)

    planner_scope = next(r for r in at.radio if r.label == "Plan for")
    planner_scope.set_value("Road").run()
    assert not at.exception
    assert any("Best time" in s.value for s in at.success)
