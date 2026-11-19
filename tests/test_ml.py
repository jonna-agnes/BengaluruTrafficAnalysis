"""Tests for the ML pipeline (features, training, forecasting) and the GenAI context.

No network calls: the LLM client is only tested for its missing-key error.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ml.features import FEATURES, TARGET, build_features, clean_events, time_split
from ml.train import make_pipeline
from simulator import SimConfig, inject_anomalies, simulate


@pytest.fixture(scope="module")
def events() -> pd.DataFrame:
    cfg = SimConfig(days=2, seed=3, duplicate_rate=0.02, invalid_rate=0.01, missing_rate=0.01)
    df = inject_anomalies(simulate(cfg), cfg)
    # Round-trip through CSV like the real pipeline: "None" strings become NaN.
    return pd.read_csv(pd.io.common.StringIO(df.to_csv(index=False)))


def test_clean_events_restores_none_and_drops_bad_rows(events):
    clean = clean_events(events)
    assert clean["event_id"].is_unique
    assert (clean["incident_type"] == "None").any()
    assert clean["incident_type"].notna().all()
    assert clean["occupancy_pct"].between(0, 100).all()
    assert set(clean["anomaly_type"]) <= {"None", "Delayed"}


def test_target_is_congestion_horizon_minutes_later(events):
    feats = build_features(clean_events(events), horizon_minutes=30)
    row = feats.dropna(subset=[TARGET]).iloc[50]
    later = feats[(feats["road_segment_id"] == row["road_segment_id"])
                  & (feats["event_ts"] == row["event_ts"] + pd.Timedelta(minutes=30))]
    assert later["congestion_level"].item() == row[TARGET]
    # The last 30 minutes of every segment have no future label.
    last_ts = feats["event_ts"].max()
    assert feats.loc[feats["event_ts"] > last_ts - pd.Timedelta(minutes=30), TARGET].isna().all()


def test_time_split_is_chronological(events):
    feats = build_features(clean_events(events)).dropna(subset=[TARGET])
    train, test = time_split(feats, 0.25)
    assert train["event_ts"].max() < test["event_ts"].min()


def test_pipeline_trains_and_predicts_valid_levels(events):
    feats = build_features(clean_events(events)).dropna(subset=[TARGET])
    train, test = time_split(feats, 0.25)
    model = make_pipeline().fit(train[FEATURES], train[TARGET])
    pred = model.predict(test[FEATURES])
    assert set(pred) <= {"Low", "Moderate", "High", "Severe"}
    assert (pred == test[TARGET]).mean() > 0.6


def test_llm_requires_api_key(monkeypatch):
    from genai.llm import LLMError, chat
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        chat([{"role": "user", "content": "hi"}])
