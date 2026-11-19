"""Send simulated traffic events to Kafka, one JSON message per event.

    python -m streaming.producer                                  # output/events/traffic_events.csv
    python -m streaming.producer --speed 300                      # replay 300x faster than real time

Messages are keyed by road_segment_id, so each road's readings stay in order within a partition.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
from confluent_kafka import Producer


def read_events(path: Path) -> pd.DataFrame:
    # Keep the literal string "None" (no incident / no anomaly); only empty cells are missing.
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])
    return df.astype(object).where(df.notna(), None).sort_values("generated_at", kind="stable")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", type=Path, default=Path("output/events/traffic_events.csv"))
    p.add_argument("--topic", default=os.getenv("KAFKA_TOPIC", "traffic-events"))
    p.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    p.add_argument("--speed", type=float, default=0, help="replay speed-up vs real time; 0 = as fast as possible")
    args = p.parse_args()

    events = read_events(args.file)
    producer = Producer({"bootstrap.servers": args.bootstrap, "linger.ms": 50, "compression.type": "zstd"})
    failures = 0

    def on_delivery(err, _msg):
        nonlocal failures
        if err:
            failures += 1

    previous = None
    for i, event in enumerate(events.to_dict(orient="records"), start=1):
        if args.speed > 0:
            now = pd.Timestamp(event["generated_at"])
            if previous is not None:
                time.sleep(max(0.0, (now - previous).total_seconds() / args.speed))
            previous = now
        producer.produce(args.topic, key=event["road_segment_id"], value=json.dumps(event, default=str),
                         on_delivery=on_delivery)
        producer.poll(0)
        if i % 10_000 == 0:
            print(f"sent {i:,} / {len(events):,}")

    producer.flush()
    print(f"sent {len(events):,} events to '{args.topic}' ({failures} delivery failures)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
