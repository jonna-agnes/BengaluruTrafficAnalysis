"""Generate simulated traffic events.

    python -m simulator                       # 7 days from 2026-07-01 -> output/events/traffic_events.csv
    python -m simulator --days 3 --start 2026-08-01 --no-anomalies
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from simulator.core import IST, SimConfig, inject_anomalies, simulate


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--start", default="2026-07-01", help="first day (IST), YYYY-MM-DD")
    p.add_argument("--interval-minutes", type=int, default=5, choices=[1, 5, 10, 15])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--no-anomalies", action="store_true", help="skip duplicate / missing / invalid records")
    p.add_argument("--out", type=Path, default=Path("output/events/traffic_events.csv"))
    args = p.parse_args()

    cfg = SimConfig(start=datetime.fromisoformat(args.start).replace(tzinfo=IST), days=args.days,
                    interval_minutes=args.interval_minutes, seed=args.seed)
    events = simulate(cfg)
    if not args.no_anomalies:
        events = inject_anomalies(events, cfg)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(args.out, index=False)
    print(f"wrote {len(events):,} events ({(events['anomaly_type'] != 'None').sum():,} with anomalies) -> {args.out}")
    print(events.loc[events["anomaly_type"] == "None", "congestion_level"].value_counts(normalize=True)
          .round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
