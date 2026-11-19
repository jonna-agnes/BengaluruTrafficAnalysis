-- Fails if any reading is physically impossible.
select event_id
from {{ ref('fact_traffic_events') }}
where vehicle_count < 0
   or avg_speed_kmph < 0
   or occupancy_pct not between 0 and 100
   or incident_duration_minutes < 0
