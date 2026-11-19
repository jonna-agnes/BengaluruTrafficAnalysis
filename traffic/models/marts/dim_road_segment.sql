-- Latest known attributes of every monitored road segment.
select
    road_segment_id,
    area,
    road_name,
    latitude,
    longitude
from {{ ref('int_events_unique') }}
where road_segment_id is not null
qualify row_number() over (partition by road_segment_id order by event_ts desc) = 1
