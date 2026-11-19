"""Score the latest observation of every road segment with the trained model.

    python -m ml.predict --data output/events

Writes output/predictions/congestion_forecast.csv: one row per segment with
the current level, the forecast level `horizon` minutes ahead, and class
probabilities.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd

from ml.features import REPO_ROOT, build_features, clean_events, load_events
from ml.train import DEFAULT_MODEL_DIR

DEFAULT_OUT = REPO_ROOT / "output" / "predictions" / "congestion_forecast.csv"
SEVERITY = {"Low": 0, "Moderate": 1, "High": 2, "Severe": 3}


def forecast(events: pd.DataFrame, model_path: Path, as_of: str | None = None) -> pd.DataFrame:
    """Forecast from each segment's latest observation (at or before `as_of`, IST if naive)."""
    bundle = joblib.load(model_path)
    pipe, horizon = bundle["pipeline"], bundle["horizon_minutes"]

    events = clean_events(events)
    if as_of:
        ts = pd.Timestamp(as_of)
        ts = ts.tz_localize("Asia/Kolkata") if ts.tzinfo is None else ts
        events = events[events["event_ts"] <= ts]
        if events.empty:
            raise ValueError(f"no events at or before {as_of}")
    df = build_features(events, horizon)
    latest = df.sort_values("event_ts").groupby("road_segment_id").tail(1).copy()

    proba = pipe.predict_proba(latest[bundle["features"]])
    classes = list(pipe.classes_)
    latest["forecast_congestion_level"] = [classes[i] for i in proba.argmax(axis=1)]
    latest["forecast_confidence"] = proba.max(axis=1).round(3)
    for i, c in enumerate(classes):
        latest[f"p_{c.lower()}"] = proba[:, i].round(3)
    latest["event_ts"] = latest["event_ts"].dt.tz_convert("Asia/Kolkata")
    latest["forecast_for"] = latest["event_ts"] + pd.Timedelta(minutes=horizon)
    latest["trend"] = (latest["forecast_congestion_level"].map(SEVERITY)
                       - latest["congestion_level"].map(SEVERITY)).map(
        lambda d: "worsening" if d > 0 else ("improving" if d < 0 else "stable"))

    cols = ["road_segment_id", "area", "road_name", "event_ts", "forecast_for",
            "avg_speed_kmph", "occupancy_pct", "weather", "incident_type",
            "congestion_level", "forecast_congestion_level", "forecast_confidence", "trend"]
    cols += [f"p_{c.lower()}" for c in classes]
    return latest[cols].sort_values(
        ["forecast_congestion_level", "forecast_confidence"],
        key=lambda s: s.map(SEVERITY) if s.name == "forecast_congestion_level" else s,
        ascending=False,
    ).reset_index(drop=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=REPO_ROOT / "output" / "events")
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL_DIR / "congestion_model.joblib")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--as-of", help="forecast from this time, e.g. 2026-07-07T08:30 (IST); default: latest")
    args = p.parse_args()

    out = forecast(load_events(args.data), args.model, args.as_of)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(out[["road_segment_id", "area", "congestion_level", "forecast_congestion_level",
               "forecast_confidence", "trend"]].head(10).to_string(index=False))
    print(f"\n{len(out)} segment forecasts -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
