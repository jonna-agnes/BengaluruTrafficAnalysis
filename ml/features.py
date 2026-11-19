"""Feature engineering for the congestion forecasting model.

Task: given what a road segment looks like *now* (time t), predict its
congestion_level at t + horizon (default 30 minutes).

Works on the simulator's CSV / JSONL / Parquet output (the same event schema
that flows through Kafka -> Spark -> S3 -> Snowflake).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
ROAD_NETWORK_CONFIG = REPO_ROOT / "config" / "road_network.json"

CONGESTION_LEVELS = ["Low", "Moderate", "High", "Severe"]
TARGET = "target_congestion_level"

CATEGORICAL_FEATURES = [
    "area", "road_type", "weather", "incident_type", "day_of_week", "congestion_level",
]
NUMERIC_FEATURES = [
    "lane_count", "speed_limit_kmph", "capacity_vehicles_per_minute",
    "is_weekend", "hour_sin", "hour_cos", "target_hour_sin", "target_hour_cos",
    "vehicle_count", "avg_speed_kmph", "occupancy_pct", "speed_ratio",
    "incident_duration_minutes",
    "vehicle_count_lag1", "avg_speed_kmph_lag1", "occupancy_pct_lag1",
    "vehicle_count_lag2", "avg_speed_kmph_lag2", "occupancy_pct_lag2",
    "vehicle_count_roll3", "avg_speed_kmph_roll3", "occupancy_pct_roll3",
    "speed_delta", "occupancy_delta",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

_LAG_COLS = ["vehicle_count", "avg_speed_kmph", "occupancy_pct"]


def load_events(path: Path | str) -> pd.DataFrame:
    """Load traffic events from a file or a folder of simulator output."""
    path = Path(path)
    if path.is_dir():
        files = (sorted(path.glob("traffic_events*.csv"))
                 + sorted(path.glob("traffic_events*.jsonl"))
                 + sorted(path.rglob("*.parquet")))
        if not files:
            raise FileNotFoundError(f"no traffic_events files in {path}")
    else:
        files = [path]

    frames = []
    for f in files:
        if f.suffix == ".csv":
            frames.append(pd.read_csv(f))
        elif f.suffix == ".jsonl":
            frames.append(pd.read_json(f, lines=True))
        else:
            frames.append(pd.read_parquet(f))
    return pd.concat(frames, ignore_index=True)


def clean_events(df: pd.DataFrame) -> pd.DataFrame:
    """Mirror the Spark job's cleaning: drop anomalies, invalid rows, duplicates."""
    df = df.copy()
    df["event_ts"] = pd.to_datetime(df["event_timestamp"], utc=True, errors="coerce")
    # pandas reads the literal string "None" in CSVs as NaN - restore it.
    for c in ("incident_type", "anomaly_type"):
        if c in df:
            df[c] = df[c].fillna("None")
    if "anomaly_type" in df:
        df = df[df["anomaly_type"].isin(["None", "Delayed"])]
    df = df.dropna(subset=["event_id", "event_ts", "road_segment_id", "area"])
    df = df[(df["vehicle_count"] >= 0) & (df["avg_speed_kmph"] >= 0)]
    df = df[df["occupancy_pct"].between(0, 100)]
    df = df[df["congestion_level"].isin(CONGESTION_LEVELS)]
    df = df.sort_values("generated_at").drop_duplicates("event_id", keep="last")
    return df.sort_values(["road_segment_id", "event_ts"]).reset_index(drop=True)


def _road_segments() -> pd.DataFrame:
    segs = json.loads(ROAD_NETWORK_CONFIG.read_text(encoding="utf-8"))["segments"]
    return pd.DataFrame(segs)[
        ["road_segment_id", "road_type", "lane_count", "speed_limit_kmph",
         "capacity_vehicles_per_minute"]
    ]


def _cyclical(hours: pd.Series) -> tuple[pd.Series, pd.Series]:
    angle = 2 * np.pi * hours / 24.0
    return np.sin(angle), np.cos(angle)


def build_features(df: pd.DataFrame, horizon_minutes: int = 30) -> pd.DataFrame:
    """Add model features to cleaned events. One row per (segment, timestamp).

    Also attaches the label (congestion level `horizon_minutes` later) where
    that future observation exists; rows without one keep a NaN target and
    are what `predict` scores.
    """
    df = df.merge(_road_segments(), on="road_segment_id", how="left")
    df["is_weekend"] = df["is_weekend"].astype(str).str.lower().eq("true").astype(int)

    local = df["event_ts"].dt.tz_convert("Asia/Kolkata")
    hour = local.dt.hour + local.dt.minute / 60.0
    df["hour_sin"], df["hour_cos"] = _cyclical(hour)
    df["target_hour_sin"], df["target_hour_cos"] = _cyclical((hour + horizon_minutes / 60.0) % 24)

    df["speed_ratio"] = df["avg_speed_kmph"] / df["speed_limit_kmph"]
    df["weather"] = df["weather"].fillna("Unknown")
    df["incident_type"] = df["incident_type"].fillna("None")
    df["incident_duration_minutes"] = df["incident_duration_minutes"].fillna(0)

    g = df.groupby("road_segment_id", sort=False)
    for c in _LAG_COLS:
        df[f"{c}_lag1"] = g[c].shift(1)
        df[f"{c}_lag2"] = g[c].shift(2)
        df[f"{c}_roll3"] = g[c].transform(lambda s: s.rolling(3, min_periods=1).mean())
    df["speed_delta"] = df["avg_speed_kmph"] - df["avg_speed_kmph_lag1"]
    df["occupancy_delta"] = df["occupancy_pct"] - df["occupancy_pct_lag1"]

    # Label: same segment, exactly horizon_minutes later (robust to any interval / gaps).
    future = df[["road_segment_id", "event_ts", "congestion_level"]].rename(
        columns={"congestion_level": TARGET})
    future["event_ts"] = future["event_ts"] - pd.Timedelta(minutes=horizon_minutes)
    return df.merge(future, on=["road_segment_id", "event_ts"], how="left")


def time_split(df: pd.DataFrame, test_fraction: float = 0.2):
    """Chronological split - no shuffling, so the test set is genuinely 'future'."""
    cutoff = df["event_ts"].quantile(1 - test_fraction)
    return df[df["event_ts"] < cutoff], df[df["event_ts"] >= cutoff]
