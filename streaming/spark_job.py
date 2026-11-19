"""Spark Structured Streaming: Kafka -> validate -> deduplicate -> 5-minute windows -> Parquet (S3 or local).

    python -m streaming.spark_job                         # S3 (TRAFFIC_S3_BUCKET, AWS_PROFILE, AWS_REGION)
    TRAFFIC_SINK=local python -m streaming.spark_job      # output/lake/ instead of S3
    TRAFFIC_ONCE=1 python -m streaming.spark_job          # process what's in Kafka now, then stop

Writes the same layout as cloud/batch_load.py:
    <lake>/raw/traffic_events/   cleaned events
    <lake>/aggregated/5min/      one row per road segment per 5-minute window
"""
from __future__ import annotations

import os
from pathlib import Path

import pyspark
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

LEVELS = ["Low", "Moderate", "High", "Severe"]

EVENT_SCHEMA = T.StructType([
    T.StructField("event_id", T.StringType()),
    T.StructField("event_timestamp", T.StringType()),
    T.StructField("area", T.StringType()),
    T.StructField("road_segment_id", T.StringType()),
    T.StructField("road_name", T.StringType()),
    T.StructField("latitude", T.DoubleType()),
    T.StructField("longitude", T.DoubleType()),
    T.StructField("vehicle_count", T.IntegerType()),
    T.StructField("avg_speed_kmph", T.DoubleType()),
    T.StructField("occupancy_pct", T.DoubleType()),
    T.StructField("congestion_level", T.StringType()),
    T.StructField("weather", T.StringType()),
    T.StructField("incident_type", T.StringType()),
    T.StructField("incident_duration_minutes", T.IntegerType()),
    T.StructField("is_weekend", T.BooleanType()),
    T.StructField("hour_of_day", T.IntegerType()),
    T.StructField("day_of_week", T.StringType()),
    T.StructField("data_source", T.StringType()),
    T.StructField("generated_at", T.StringType()),
    T.StructField("anomaly_type", T.StringType()),
])


def lake_path() -> str:
    if os.getenv("TRAFFIC_SINK", "s3") == "local":
        return Path(os.getenv("TRAFFIC_LAKE_DIR", "output/lake")).resolve().as_uri()
    bucket = os.environ.get("TRAFFIC_S3_BUCKET")
    if not bucket:
        raise SystemExit("Set TRAFFIC_S3_BUCKET (or TRAFFIC_SINK=local)")
    return f"s3a://{bucket}"


def spark_session(use_s3: bool) -> SparkSession:
    packages = [f"org.apache.spark:spark-sql-kafka-0-10_2.13:{pyspark.__version__}"]
    builder = (SparkSession.builder.appName("bengaluru-traffic-stream")
               .config("spark.sql.shuffle.partitions", "4")
               .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "2g"))
               # standard UTC-adjusted timestamps: read as real timestamps by Snowflake and DuckDB
               .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS"))
    if use_s3:
        packages.append("org.apache.hadoop:hadoop-aws:3.5.0")  # must match pyspark's bundled Hadoop
        builder = (builder
                   .config("spark.hadoop.fs.s3a.aws.credentials.provider",
                           "software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider")  # honours AWS_PROFILE
                   .config("spark.hadoop.fs.s3a.endpoint.region", os.getenv("AWS_REGION", "ap-south-1")))
    return builder.config("spark.jars.packages", ",".join(packages)).getOrCreate()


def parse(kafka: DataFrame) -> DataFrame:
    events = kafka.select(F.from_json(F.col("value").cast("string"), EVENT_SCHEMA).alias("e")).select("e.*")
    return events.withColumn("event_ts", F.to_timestamp("event_timestamp"))


def is_valid() -> F.Column:
    """Rows a downstream consumer can trust: keys present, values physically possible."""
    return (F.col("event_id").isNotNull() & F.col("event_ts").isNotNull()
            & F.col("area").isNotNull() & F.col("road_segment_id").isNotNull()
            & (F.col("vehicle_count") >= 0) & (F.col("avg_speed_kmph") >= 0)
            & F.col("occupancy_pct").between(0, 100)
            & F.col("congestion_level").isin(LEVELS))


def five_minute_windows(events: DataFrame) -> DataFrame:
    rank = F.array_position(F.array(*[F.lit(l) for l in LEVELS]), F.col("congestion_level"))
    return (events
            .withWatermark("event_ts", "10 minutes")
            .dropDuplicatesWithinWatermark(["event_id"])
            .groupBy(F.window("event_ts", "5 minutes"), "area", "road_segment_id", "road_name")
            .agg(F.count("*").alias("total_events"),
                 F.round(F.avg("vehicle_count"), 2).alias("avg_vehicle_count"),
                 F.round(F.avg("avg_speed_kmph"), 2).alias("avg_speed_kmph"),
                 F.round(F.avg("occupancy_pct"), 2).alias("avg_occupancy_pct"),
                 F.max(rank).alias("peak_rank"))
            .select(F.col("window.start").alias("window_start"), F.col("window.end").alias("window_end"),
                    "area", "road_segment_id", "road_name", "total_events", "avg_vehicle_count",
                    "avg_speed_kmph", "avg_occupancy_pct",
                    F.element_at(F.array(*[F.lit(l) for l in LEVELS]), F.col("peak_rank").cast("int"))
                     .alias("peak_congestion_level")))


def write(df: DataFrame, path: str, checkpoint: str, name: str, once: bool):
    writer = (df.writeStream.queryName(name).format("parquet").outputMode("append")
              .option("path", path).option("checkpointLocation", checkpoint))
    return (writer.trigger(availableNow=True) if once else writer).start()


def main() -> None:
    lake = lake_path()
    spark = spark_session(use_s3=lake.startswith("s3a://"))
    spark.sparkContext.setLogLevel("WARN")

    kafka = (spark.readStream.format("kafka")
             .option("kafka.bootstrap.servers", os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
             .option("subscribe", os.getenv("KAFKA_TOPIC", "traffic-events"))
             .option("startingOffsets", os.getenv("KAFKA_STARTING_OFFSETS", "earliest"))
             .option("maxOffsetsPerTrigger", 5000)
             .load())
    valid = parse(kafka).where(is_valid())
    once = os.getenv("TRAFFIC_ONCE") == "1"

    queries = [
        write(valid, f"{lake}/raw/traffic_events/", f"{lake}/_checkpoints/raw/", "raw_events", once),
        write(five_minute_windows(valid), f"{lake}/aggregated/5min/", f"{lake}/_checkpoints/5min/",
              "five_minute_metrics", once),
    ]
    print(f"streaming to {lake}")
    for q in queries:
        q.awaitTermination()


if __name__ == "__main__":
    main()
