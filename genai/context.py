"""Turn raw events + ML forecasts into a compact, factual context for the LLM.

The LLM never sees raw rows - only aggregates computed here with pandas, so
every number it quotes is traceable and the prompt stays small.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ml.features import REPO_ROOT, clean_events, load_events

SEVERITY_RANK = {"Low": 1, "Moderate": 2, "High": 3, "Severe": 4}
METRICS_PATH = REPO_ROOT / "models" / "metrics.json"
FORECAST_PATH = REPO_ROOT / "output" / "predictions" / "congestion_forecast.csv"


def _table(df: pd.DataFrame) -> str:
    return df.to_string(index=False)


def build_context(data_path: Path | str, forecast_path: Path = FORECAST_PATH,
                  metrics_path: Path = METRICS_PATH) -> str:
    df = clean_events(load_events(data_path))
    df["rank"] = df["congestion_level"].map(SEVERITY_RANK)
    df["local_ts"] = df["event_ts"].dt.tz_convert("Asia/Kolkata")
    df["date"] = df["local_ts"].dt.date
    df["is_congested"] = df["congestion_level"].isin(["High", "Severe"])

    parts = [
        "DATA NOTE: synthetic simulator data for Bengaluru (not real sensor readings).",
        f"PERIOD: {df['local_ts'].min():%Y-%m-%d %H:%M} to {df['local_ts'].max():%Y-%m-%d %H:%M} IST; "
        f"{df['road_segment_id'].nunique()} road segments in {df['area'].nunique()} areas; "
        f"{len(df):,} observations.",
    ]

    overall = df["congestion_level"].value_counts(normalize=True).mul(100).round(1)
    parts.append("OVERALL CONGESTION MIX (% of observations): "
                 + ", ".join(f"{k} {v}%" for k, v in overall.items()))

    area = (df.groupby("area")
              .agg(avg_speed_kmph=("avg_speed_kmph", "mean"),
                   avg_occupancy_pct=("occupancy_pct", "mean"),
                   avg_congestion_rank=("rank", "mean"),
                   pct_high_or_severe=("is_congested", "mean"),
                   total_vehicles=("vehicle_count", "sum"))
              .sort_values("avg_congestion_rank", ascending=False))
    area["pct_high_or_severe"] *= 100
    parts.append("AREA SUMMARY (sorted worst first):\n" + _table(area.round(2).reset_index()))

    wk = df[df["is_weekend"].astype(str).str.lower() != "true"]
    hourly = (wk.groupby(wk["local_ts"].dt.hour)
                .agg(avg_speed_kmph=("avg_speed_kmph", "mean"),
                     pct_high_or_severe=("is_congested", "mean")))
    hourly["pct_high_or_severe"] *= 100
    peaks = hourly.sort_values("pct_high_or_severe", ascending=False).head(6)
    parts.append("WEEKDAY PEAK HOURS (hour of day IST, top 6 by % High/Severe):\n"
                 + _table(peaks.round(1).reset_index(names="hour")))

    area_peak = (wk.groupby(["area", wk["local_ts"].dt.hour])["rank"].mean()
                   .reset_index(name="avg_rank")
                   .sort_values("avg_rank", ascending=False)
                   .groupby("area").head(1)
                   .rename(columns={"local_ts": "worst_hour"}))
    parts.append("WORST WEEKDAY HOUR PER AREA:\n" + _table(area_peak.round(2)))

    weather = (df.groupby("weather")
                 .agg(avg_speed_kmph=("avg_speed_kmph", "mean"),
                      pct_high_or_severe=("is_congested", "mean"),
                      observations=("event_id", "count")))
    weather["pct_high_or_severe"] *= 100
    parts.append("WEATHER IMPACT:\n" + _table(weather.round(1).reset_index()))

    inc = df[df["incident_type"] != "None"]
    if not inc.empty:
        incidents = (inc.groupby("incident_type")
                       .agg(observations=("event_id", "count"),
                            avg_speed_kmph=("avg_speed_kmph", "mean"),
                            segments_affected=("road_segment_id", "nunique")))
        hot = (inc.groupby(["area", "road_name"]).size()
                  .sort_values(ascending=False).head(5).reset_index(name="incident_observations"))
        parts.append("INCIDENTS (vs overall avg speed "
                     f"{df['avg_speed_kmph'].mean():.1f} km/h):\n" + _table(incidents.round(1).reset_index())
                     + "\nTOP INCIDENT ROADS:\n" + _table(hot))

    seg = (df.groupby(["road_segment_id", "area", "road_name"])
             .agg(avg_rank=("rank", "mean"), avg_speed_kmph=("avg_speed_kmph", "mean"))
             .sort_values("avg_rank", ascending=False).head(5))
    parts.append("TOP 5 WORST ROAD SEGMENTS:\n" + _table(seg.round(2).reset_index()))

    daily = (df.groupby("date")
               .agg(avg_speed_kmph=("avg_speed_kmph", "mean"),
                    pct_high_or_severe=("is_congested", "mean")))
    daily["pct_high_or_severe"] *= 100
    parts.append("DAILY TREND:\n" + _table(daily.round(1).reset_index()))

    if Path(metrics_path).exists():
        m = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
        parts.append(
            f"ML MODEL: forecasts congestion level {m['horizon_minutes']} min ahead per segment. "
            f"Held-out accuracy {m['model']['accuracy']:.1%} (macro-F1 {m['model']['macro_f1']:.2f}) vs "
            f"persistence baseline {m['persistence_baseline']['accuracy']:.1%}.")

    if Path(forecast_path).exists():
        fc = pd.read_csv(forecast_path)
        cols = ["road_segment_id", "area", "road_name", "congestion_level",
                "forecast_congestion_level", "forecast_confidence", "trend", "forecast_for"]
        parts.append("LATEST ML FORECAST (current level -> forecast level):\n" + _table(fc[cols]))

    return "\n\n".join(parts)


if __name__ == "__main__":
    import sys
    print(build_context(sys.argv[1] if len(sys.argv) > 1 else REPO_ROOT / "output" / "events"))
