-- 5-minute window metrics with a numeric congestion rank (1 = Low ... 4 = Severe).
with source as (
    select * from {{ source('aggregated', 'TRAFFIC_METRICS_5MIN') }}
),

labelled as (
    select
        window_start,
        window_end,
        nullif(trim(area), '')               as area,
        nullif(trim(road_segment_id), '')    as road_segment_id,
        nullif(trim(road_name), '')          as road_name,
        total_events,
        avg_vehicle_count,
        avg_speed_kmph,
        avg_occupancy_pct,
        case lower(trim(peak_congestion_level))
            when 'low'      then 'Low'
            when 'moderate' then 'Moderate'
            when 'medium'   then 'Moderate'
            when 'high'     then 'High'
            when 'severe'   then 'Severe'
        end                                  as peak_congestion_level
    from source
)

select
    *,
    case peak_congestion_level
        when 'Low' then 1 when 'Moderate' then 2 when 'High' then 3 when 'Severe' then 4
    end as peak_congestion_rank
from labelled
