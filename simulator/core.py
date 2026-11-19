"""Traffic model: demand curves -> flow -> speed (BPR) -> occupancy -> congestion level.

For every road segment and every interval:

1. demand   = hourly demand curve (by area type, weekday/weekend) x day factor
              x segment demand scale x slow random drift
2. capacity = segment capacity x weather factor x incident factor
3. x        = demand / capacity                     (degree of saturation)
4. vehicles = served flow, min(demand, capacity), with counting noise
5. speed    = free-flow speed / (1 + 0.15 * x^4)    (BPR speed-flow function)
6. occupancy from density = flow / speed / lanes, times effective vehicle length
7. congestion level from speed as a share of the speed limit

Weather is city-wide (hourly Markov chain, monsoon month). Incidents are per segment.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30))
NETWORK_FILE = Path(__file__).resolve().parent.parent / "config" / "road_network.json"

EVENT_COLUMNS = [
    "event_id", "event_timestamp", "area", "road_segment_id", "road_name", "latitude", "longitude",
    "vehicle_count", "avg_speed_kmph", "occupancy_pct", "congestion_level", "weather",
    "incident_type", "incident_duration_minutes", "is_weekend", "hour_of_day", "day_of_week",
    "data_source", "generated_at", "anomaly_type",
]

WEATHER_STATES = ["Clear", "Cloudy", "Rain", "Heavy_Rain"]
# hourly transition probabilities (rows: from, cols: to) for a monsoon month
WEATHER_TRANSITIONS = np.array([
    [0.80, 0.17, 0.03, 0.00],
    [0.25, 0.60, 0.13, 0.02],
    [0.08, 0.30, 0.50, 0.12],
    [0.02, 0.10, 0.48, 0.40],
])
WEATHER_CAPACITY = {"Clear": 1.00, "Cloudy": 0.97, "Rain": 0.84, "Heavy_Rain": 0.62}
WEATHER_SPEED = {"Clear": 1.00, "Cloudy": 0.98, "Rain": 0.88, "Heavy_Rain": 0.72}

# incident type -> (chance per segment-hour, capacity factor, speed factor, duration range in minutes)
# Capacity loss bites at busy times; the speed factor slows everyone even on an empty road
# (rubbernecking at an accident, wading through waterlogging).
INCIDENTS = {
    "Vehicle_Breakdown": (0.006, 0.75, 0.85, (15, 60)),
    "Accident": (0.002, 0.50, 0.70, (30, 120)),
    "Waterlogging": (0.060, 0.55, 0.55, (45, 150)),  # only during Heavy_Rain
}

VEHICLE_LENGTH_M = 6.5  # effective length (vehicle + gap) seen by a loop detector
# Peak demand relative to capacity: at the busiest hour a demand-scale-1.0 road is asked to carry
# 1.55x what it can serve, which is what makes rush-hour speeds collapse in the BPR curve.
PEAK_SATURATION = 1.55


@dataclass(frozen=True)
class SimConfig:
    start: datetime = datetime(2026, 7, 1, tzinfo=IST)
    days: int = 7
    interval_minutes: int = 5
    seed: int = 42
    duplicate_rate: float = 0.010      # resent copies of valid events
    missing_rate: float = 0.005        # a required field left empty
    invalid_rate: float = 0.005        # an impossible value


def load_network(path: Path = NETWORK_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _weather_by_hour(hours: int, rng: np.random.Generator) -> list[str]:
    state, out = 0, []
    for _ in range(hours):
        out.append(WEATHER_STATES[state])
        state = rng.choice(4, p=WEATHER_TRANSITIONS[state])
    return out


def _congestion_level(speed_ratio: float) -> str:
    if speed_ratio >= 0.70:
        return "Low"
    if speed_ratio >= 0.50:
        return "Moderate"
    if speed_ratio >= 0.30:
        return "High"
    return "Severe"


def simulate(cfg: SimConfig = SimConfig(), network: dict | None = None) -> pd.DataFrame:
    """Simulate clean events for every segment and interval (no anomalies)."""
    net = network or load_network()
    rng = np.random.default_rng(cfg.seed)
    steps_per_hour = 60 // cfg.interval_minutes
    n_steps = cfg.days * 24 * steps_per_hour
    weather = _weather_by_hour(cfg.days * 24 + 1, rng)
    times = [cfg.start + timedelta(minutes=cfg.interval_minutes * i) for i in range(n_steps)]

    rows = []
    for seg in net["segments"]:
        curves = net["hourly_demand"][net["area_profiles"][seg["area"]]]
        cap_per_step = seg["capacity_vehicles_per_minute"] * cfg.interval_minutes
        free_flow = seg["speed_limit_kmph"] * rng.uniform(0.86, 0.94)
        drift, incident, incident_left = 0.0, None, 0

        for i, t in enumerate(times):
            hour_idx = i // steps_per_hour
            wx = weather[hour_idx]
            weekend = t.weekday() >= 5
            curve = curves["weekend" if weekend else "weekday"]
            frac = (t.minute / 60.0)
            base = curve[t.hour] * (1 - frac) + curve[(t.hour + 1) % 24] * frac   # smooth between hours

            # incidents: start at most one at a time, roll once per hour
            if incident_left <= 0:
                incident = None
                if t.minute == 0:
                    for name, (p, _, _, (lo, hi)) in INCIDENTS.items():
                        if name == "Waterlogging" and wx != "Heavy_Rain":
                            continue
                        if rng.random() < p:
                            incident, incident_left = name, int(rng.integers(lo, hi + 1))
                            break
            incident_factor = INCIDENTS[incident][1] if incident else 1.0
            incident_speed = INCIDENTS[incident][2] if incident else 1.0

            drift = 0.85 * drift + rng.normal(0, 0.03)                         # slowly varying noise
            demand = (cap_per_step * PEAK_SATURATION * base * net["day_factor"][t.strftime("%A")]
                      * seg["demand_scale"] * (1 + drift))
            capacity = cap_per_step * WEATHER_CAPACITY[wx] * incident_factor
            x = demand / capacity
            served = min(demand, capacity) * rng.normal(1.0, 0.04)
            vehicles = max(0, int(round(served)))

            speed = free_flow * WEATHER_SPEED[wx] * incident_speed / (1 + 0.15 * x ** 4) * rng.normal(1.0, 0.03)
            speed = float(np.clip(speed, 3.0, seg["speed_limit_kmph"]))
            flow_per_hour_lane = vehicles * (60 / cfg.interval_minutes) / seg["lane_count"]
            density = flow_per_hour_lane / speed                              # vehicles per km per lane
            occupancy = float(np.clip(density * VEHICLE_LENGTH_M / 10, 0.0, 98.0))

            rows.append({
                "event_id": f"{seg['road_segment_id']}-{t:%Y%m%d%H%M}",
                "event_timestamp": t.isoformat(),
                "area": seg["area"],
                "road_segment_id": seg["road_segment_id"],
                "road_name": seg["road_name"],
                "latitude": seg["latitude"],
                "longitude": seg["longitude"],
                "vehicle_count": vehicles,
                "avg_speed_kmph": round(speed, 1),
                "occupancy_pct": round(occupancy, 1),
                "congestion_level": _congestion_level(speed / seg["speed_limit_kmph"]),
                "weather": wx,
                "incident_type": incident or "None",
                "incident_duration_minutes": incident_left if incident else 0,
                "is_weekend": weekend,
                "hour_of_day": t.hour,
                "day_of_week": t.strftime("%A"),
                "data_source": "simulator",
                "generated_at": (t + timedelta(minutes=cfg.interval_minutes,
                                               seconds=float(rng.uniform(2, 40)))).isoformat(timespec="milliseconds"),
                "anomaly_type": "None",
            })
            incident_left -= cfg.interval_minutes
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def inject_anomalies(df: pd.DataFrame, cfg: SimConfig = SimConfig()) -> pd.DataFrame:
    """Add realistic data-quality problems for the cleaning step to catch."""
    rng = np.random.default_rng(cfg.seed + 1)
    df = df.copy()
    n = len(df)
    picks = rng.permutation(n)
    n_missing, n_invalid = int(n * cfg.missing_rate), int(n * cfg.invalid_rate)
    missing, invalid = picks[:n_missing], picks[n_missing:n_missing + n_invalid]

    for i in missing:
        col = rng.choice(["road_name", "occupancy_pct", "area"])
        df.at[i, col] = None
        df.at[i, "anomaly_type"] = "Missing_Field"
    for i in invalid:
        if rng.random() < 0.5:
            df.at[i, "avg_speed_kmph"] = -round(float(rng.uniform(5, 40)), 1)
        else:
            df.at[i, "occupancy_pct"] = round(float(rng.uniform(101, 160)), 1)
        df.at[i, "anomaly_type"] = "Invalid_Value"

    clean_rows = df[df["anomaly_type"] == "None"]
    dup = clean_rows.sample(n=int(n * cfg.duplicate_rate), random_state=cfg.seed).copy()
    dup["generated_at"] = [(datetime.fromisoformat(g) + timedelta(seconds=float(rng.uniform(1, 30))))
                           .isoformat(timespec="milliseconds") for g in dup["generated_at"]]
    dup["anomaly_type"] = "Duplicate"
    return (pd.concat([df, dup], ignore_index=True)
              .sort_values(["event_timestamp", "road_segment_id"], kind="stable")
              .reset_index(drop=True))
