"""Snapshot the pipeline outputs into streamlit_app/data/ so the app runs anywhere (no cloud logins).

    python streamlit_app/export_data.py

Inputs: the dbt marts CSV export (output/powerbi), the ML forecast and the GenAI briefing.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "output" / "powerbi"
OUT = Path(__file__).resolve().parent / "data"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Asia/Kolkata'")  # store Bengaluru wall-clock times
    csv = lambda name: f"read_csv('{(MARTS / name).as_posix()}', header = true)"

    con.execute(f"""
        COPY (
            SELECT f.window_start::TIMESTAMPTZ::TIMESTAMP AS window_start,
                   d.date_day, d.day_name, d.day_of_week, d.is_weekend,
                   f.area, f.road_segment_id, f.road_name, r.latitude, r.longitude,
                   f.avg_vehicle_count * f.total_events AS vehicles,
                   f.avg_speed_kmph, f.avg_occupancy_pct,
                   f.peak_congestion_rank, f.peak_congestion_level
            FROM {csv('fact_traffic_5min.csv')} f
            JOIN {csv('dim_date.csv')} d USING (date_key)
            JOIN {csv('dim_road_segment.csv')} r USING (road_segment_id)
        ) TO '{(OUT / 'traffic_5min.parquet').as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    # Event-level weather / incident impact, pre-aggregated (keeps the snapshot small)
    con.execute(f"""
        COPY (
            SELECT d.date_day, r.area, w.weather, coalesce(i.incident_type, 'None') AS incident_type,
                   count(*) AS events, sum(e.avg_speed_kmph) AS speed_sum,
                   sum(CASE WHEN e.congestion_level IN ('High', 'Severe') THEN 1 ELSE 0 END) AS high_severe
            FROM {csv('fact_traffic_events.csv')} e
            JOIN {csv('dim_date.csv')} d USING (date_key)
            JOIN {csv('dim_road_segment.csv')} r USING (road_segment_id)
            LEFT JOIN {csv('dim_weather.csv')} w USING (weather_key)
            LEFT JOIN {csv('dim_incident.csv')} i USING (incident_key)
            GROUP BY ALL
        ) TO '{(OUT / 'event_impact.parquet').as_posix()}' (FORMAT parquet)
    """)

    for src, dst in [
        (ROOT / "output" / "predictions" / "congestion_forecast.csv", "congestion_forecast.csv"),
        (ROOT / "output" / "reports" / "traffic_briefing.md", "traffic_briefing.md"),
        (ROOT / "models" / "metrics.json", "metrics.json"),
    ]:
        if src.exists():
            shutil.copyfile(src, OUT / dst)

    for f in sorted(OUT.iterdir()):
        print(f"{f.name:28} {f.stat().st_size / 1024:8.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
