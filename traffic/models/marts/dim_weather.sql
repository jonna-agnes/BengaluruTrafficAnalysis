select distinct
    {{ text_key('weather') }} as weather_key,
    weather
from {{ ref('int_events_unique') }}
