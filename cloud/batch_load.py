"""Batch replay of generated traffic events into the S3 data lake (no Kafka/Spark needed).

Applies the same cleaning, de-duplication and 5-minute aggregation as
pyspark_transformation/trans.py and writes Parquet to the same S3 layout:

    s3://<bucket>/raw/traffic_events/part-<run>.parquet
    s3://<bucket>/aggregated/5min/part-<run>.parquet

so Snowflake (COPY INTO from the stages) and the dbt `cloud` DuckDB target read it unchanged.
Use the Spark job for true streaming; use this on small machines or to backfill.

    python -m cloud.batch_load --input output/events/traffic_events.csv
    python -m cloud.batch_load --input ... --dest output/local_lake     # local folder instead of S3
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from cloud import config

CLEAN_SQL = """
WITH src AS (
    SELECT * FROM read_csv({files}, all_varchar = true, header = true)
),
typed AS (
    SELECT
        NULLIF(event_id, '')                         AS event_id,
        event_timestamp,
        TRY_CAST(event_timestamp AS TIMESTAMPTZ)     AS event_ts,
        NULLIF(area, '')                             AS area,
        NULLIF(road_segment_id, '')                  AS road_segment_id,
        NULLIF(road_name, '')                        AS road_name,
        TRY_CAST(latitude AS DOUBLE)                 AS latitude,
        TRY_CAST(longitude AS DOUBLE)                AS longitude,
        TRY_CAST(vehicle_count AS INTEGER)           AS vehicle_count,
        TRY_CAST(avg_speed_kmph AS DOUBLE)           AS avg_speed_kmph,
        TRY_CAST(occupancy_pct AS DOUBLE)            AS occupancy_pct,
        congestion_level,
        NULLIF(weather, '')                          AS weather,
        CASE WHEN incident_type IN ('Nan', 'nan', '') THEN NULL ELSE incident_type END AS incident_type,
        TRY_CAST(incident_duration_minutes AS INTEGER) AS incident_duration_minutes,
        TRY_CAST(is_weekend AS BOOLEAN)              AS is_weekend,
        TRY_CAST(hour_of_day AS INTEGER)             AS hour_of_day,
        NULLIF(day_of_week, '')                      AS day_of_week,
        NULLIF(data_source, '')                      AS data_source,
        NULLIF(generated_at, '')                     AS generated_at,
        CASE WHEN anomaly_type IN ('Nan', 'nan', '') THEN NULL ELSE anomaly_type END AS anomaly_type
    FROM src
)
-- same predicate as the Spark job's clean_event filter
SELECT * FROM typed
WHERE event_id IS NOT NULL AND event_ts IS NOT NULL AND area IS NOT NULL
  AND road_segment_id IS NOT NULL
  AND vehicle_count >= 0 AND avg_speed_kmph >= 0
  AND occupancy_pct IS NOT NULL AND occupancy_pct BETWEEN 0 AND 100
  AND congestion_level IN ('Low', 'Moderate', 'High', 'Severe')
"""

METRICS_SQL = """
WITH dedup AS (   -- Spark: dropDuplicatesWithinWatermark(["event_id"])
    SELECT * FROM clean_events
    QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY generated_at) = 1
),
ranked AS (
    SELECT *, time_bucket(INTERVAL 5 MINUTE, event_ts) AS window_start,
           CASE congestion_level WHEN 'Low' THEN 1 WHEN 'Moderate' THEN 2
                                 WHEN 'High' THEN 3 WHEN 'Severe' THEN 4 END AS congestion_rank
    FROM dedup
)
SELECT
    window_start,
    window_start + INTERVAL 5 MINUTE      AS window_end,
    area, road_segment_id, road_name,
    COUNT(*)                              AS total_events,
    ROUND(AVG(vehicle_count), 2)          AS avg_vehicle_count,
    ROUND(AVG(avg_speed_kmph), 2)         AS avg_speed_kmph,
    ROUND(AVG(occupancy_pct), 2)          AS avg_occupancy_pct,
    CASE MAX(congestion_rank) WHEN 1 THEN 'Low' WHEN 2 THEN 'Moderate'
                              WHEN 3 THEN 'High' WHEN 4 THEN 'Severe' END AS peak_congestion_level
FROM ranked
GROUP BY ALL
"""


def connect_s3(con: duckdb.DuckDBPyConnection, aws: config.AwsSettings) -> str:
    """Give DuckDB the AWS profile's credentials; return the bucket name."""
    from cloud.setup import aws_session

    session, account_id = aws_session(aws)
    creds = session.get_credentials().get_frozen_credentials()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE OR REPLACE SECRET traffic_s3 (TYPE s3, KEY_ID ?, SECRET ?, SESSION_TOKEN ?, REGION ?)",
        [creds.access_key, creds.secret_key, creds.token or "", aws.region],
    )
    return aws.bucket_name(account_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", nargs="+", type=Path, default=[Path("output/events/traffic_events.csv")])
    parser.add_argument("--dest", help="local folder instead of S3 (default: the project S3 bucket)")
    args = parser.parse_args()

    aws, _ = config.load()
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")  # Parquet stores UTC instants, like Spark
    if os.getenv("DUCKDB_EXTENSION_DIRECTORY"):
        con.execute(f"SET extension_directory = '{os.environ['DUCKDB_EXTENSION_DIRECTORY']}'")

    if args.dest:
        base = Path(args.dest).resolve().as_posix()
        for sub in ("raw/traffic_events", "aggregated/5min"):
            Path(base, sub).mkdir(parents=True, exist_ok=True)
    else:
        base = f"s3://{connect_s3(con, aws)}"

    files = "[" + ", ".join(f"'{p.resolve().as_posix()}'" for p in args.input) + "]"
    con.execute(f"CREATE TEMP TABLE clean_events AS {CLEAN_SQL.format(files=files)}")
    con.execute(f"CREATE TEMP TABLE metrics AS {METRICS_SQL}")

    total = con.execute(f"SELECT COUNT(*) FROM read_csv({files}, all_varchar = true)").fetchone()[0]
    kept = con.execute("SELECT COUNT(*) FROM clean_events").fetchone()[0]
    windows = con.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]

    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    raw_path = f"{base}/raw/traffic_events/part-{run}.parquet"
    agg_path = f"{base}/aggregated/5min/part-{run}.parquet"
    con.execute(f"COPY clean_events TO '{raw_path}' (FORMAT parquet, COMPRESSION zstd)")
    con.execute(f"COPY metrics TO '{agg_path}' (FORMAT parquet, COMPRESSION zstd)")

    print(f"read {total:,} events, kept {kept:,} after cleaning ({total - kept:,} rejected)")
    print(f"wrote {kept:,} rows  -> {raw_path}")
    print(f"wrote {windows:,} 5-min windows -> {agg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
