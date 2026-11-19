-- Grain: one road segment x one 5-minute window.
select
    {{ date_key('cast(window_start as date)') }}  as date_key,
    road_segment_id,
    window_start,
    window_end,
    area,
    road_name,
    total_events,
    avg_vehicle_count,
    avg_speed_kmph,
    avg_occupancy_pct,
    peak_congestion_rank,
    peak_congestion_level
from {{ ref('stg_windows_5min') }}
