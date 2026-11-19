"""Tests for the traffic simulator: schema, determinism, realism and injected anomalies."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from simulator import EVENT_COLUMNS, SimConfig, inject_anomalies, load_network, simulate
from simulator.core import IST

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schemas" / "traffic_event.schema.json").read_text())
CFG = SimConfig(start=datetime(2026, 7, 6, tzinfo=IST), days=2, seed=7)   # Monday + Tuesday
RANK = {"Low": 1, "Moderate": 2, "High": 3, "Severe": 4}


@pytest.fixture(scope="module")
def clean() -> pd.DataFrame:
    return simulate(CFG)


@pytest.fixture(scope="module")
def dirty(clean) -> pd.DataFrame:
    return inject_anomalies(clean, CFG)


def test_one_event_per_segment_and_interval(clean):
    segments = len(load_network()["segments"])
    assert len(clean) == segments * CFG.days * 24 * (60 // CFG.interval_minutes)
    assert clean["event_id"].is_unique
    assert list(clean.columns) == EVENT_COLUMNS


def test_clean_events_match_schema(clean):
    validator = Draft202012Validator(SCHEMA)
    for record in clean.sample(500, random_state=1).to_dict(orient="records"):
        errors = list(validator.iter_errors(record))
        assert not errors, (record["event_id"], [e.message for e in errors])


def test_same_seed_same_data():
    a, b = simulate(SimConfig(days=1, seed=3)), simulate(SimConfig(days=1, seed=3))
    pd.testing.assert_frame_equal(a.drop(columns="generated_at"), b.drop(columns="generated_at"))
    assert not a["avg_speed_kmph"].equals(simulate(SimConfig(days=1, seed=4))["avg_speed_kmph"])


def test_values_are_physically_plausible(clean):
    net = {s["road_segment_id"]: s for s in load_network()["segments"]}
    limit = clean["road_segment_id"].map(lambda s: net[s]["speed_limit_kmph"])
    assert (clean["avg_speed_kmph"] > 0).all()
    assert (clean["avg_speed_kmph"] <= limit).all()
    assert clean["occupancy_pct"].between(0, 100).all()
    assert (clean["vehicle_count"] >= 0).all()


def test_rush_hour_is_more_congested_than_night(clean):
    rank = clean["congestion_level"].map(RANK)
    peak = rank[clean["hour_of_day"].isin([8, 9, 17, 18])].mean()
    night = rank[clean["hour_of_day"].isin([1, 2, 3, 4])].mean()
    assert peak > night + 0.5


def test_silk_board_is_busier_than_mg_road(clean):
    rank = clean.assign(r=clean["congestion_level"].map(RANK)).groupby("area")["r"].mean()
    assert rank["Silk Board"] > rank["MG Road"]


def test_rain_lowers_speed():
    df = simulate(SimConfig(days=7, seed=11))
    by_weather = df.groupby("weather")["avg_speed_kmph"].mean()
    assert by_weather["Rain"] < by_weather["Clear"]


def test_anomalies_are_injected_and_labelled(clean, dirty):
    counts = dirty["anomaly_type"].value_counts()
    assert counts["Duplicate"] == int(len(clean) * CFG.duplicate_rate)
    assert counts["Missing_Field"] == int(len(clean) * CFG.missing_rate)
    assert counts["Invalid_Value"] == int(len(clean) * CFG.invalid_rate)

    dups = dirty[dirty["anomaly_type"] == "Duplicate"]
    assert dups["event_id"].isin(clean["event_id"]).all()          # same id as an original reading

    invalid = dirty[dirty["anomaly_type"] == "Invalid_Value"]
    assert ((invalid["avg_speed_kmph"] < 0) | (invalid["occupancy_pct"] > 100)).all()

    missing = dirty[dirty["anomaly_type"] == "Missing_Field"]
    assert missing[["road_name", "occupancy_pct", "area"]].isna().any(axis=1).all()
