-- Grain: one sensor reading (road segment x interval).
select
    event_id,
    {{ date_key('cast(event_ts as date)') }}  as date_key,
    road_segment_id,
    {{ text_key('weather') }}                 as weather_key,
    {{ text_key('incident_type') }}           as incident_key,
    event_ts,
    vehicle_count,
    avg_speed_kmph,
    occupancy_pct,
    congestion_level,
    incident_duration_minutes
from {{ ref('int_events_unique') }}
