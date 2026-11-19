-- Typed, trimmed sensor readings with standard labels.
with source as (
    select * from {{ source('raw', 'RAW_TRAFFIC_DATA') }}
)

select
    nullif(trim(event_id), '')            as event_id,
    event_ts,
    nullif(trim(area), '')                as area,
    nullif(trim(road_segment_id), '')     as road_segment_id,
    nullif(trim(road_name), '')           as road_name,
    latitude,
    longitude,
    vehicle_count,
    avg_speed_kmph,
    occupancy_pct,
    case lower(trim(congestion_level))
        when 'low'      then 'Low'
        when 'moderate' then 'Moderate'
        when 'medium'   then 'Moderate'
        when 'high'     then 'High'
        when 'severe'   then 'Severe'
    end                                   as congestion_level,
    coalesce(nullif(trim(weather), ''), 'Unknown')      as weather,
    coalesce(nullif(trim(incident_type), ''), 'None')   as incident_type,
    coalesce(incident_duration_minutes, 0)              as incident_duration_minutes,
    generated_at
from source
