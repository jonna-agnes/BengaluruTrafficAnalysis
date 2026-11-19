-- One row per event_id: a resent reading replaces the earlier copy.
select *
from {{ ref('stg_events') }}
where event_id is not null
qualify row_number() over (partition by event_id order by generated_at desc) = 1
