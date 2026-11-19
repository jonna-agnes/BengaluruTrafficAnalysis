select distinct
    {{ text_key('incident_type') }} as incident_key,
    incident_type
from {{ ref('int_events_unique') }}
