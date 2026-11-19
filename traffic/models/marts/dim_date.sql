-- Every calendar day (IST) that appears in either fact table.
with days as (
    select distinct cast(event_ts as date) as date_day from {{ ref('int_events_unique') }}
    union
    select distinct cast(window_start as date) from {{ ref('stg_windows_5min') }}
),

attributes as (
    select
        date_day,
        {{ iso_weekday('date_day') }} as iso_dow
    from days
    where date_day is not null
)

select
    {{ date_key('date_day') }}                                   as date_key,
    date_day,
    year(date_day)                                               as year,
    quarter(date_day)                                            as quarter,
    month(date_day)                                              as month,
    case month(date_day)
        when 1 then 'January' when 2 then 'February' when 3 then 'March' when 4 then 'April'
        when 5 then 'May' when 6 then 'June' when 7 then 'July' when 8 then 'August'
        when 9 then 'September' when 10 then 'October' when 11 then 'November' else 'December'
    end                                                          as month_name,
    day(date_day)                                                as day_of_month,
    iso_dow                                                      as day_of_week,
    case iso_dow
        when 1 then 'Monday' when 2 then 'Tuesday' when 3 then 'Wednesday' when 4 then 'Thursday'
        when 5 then 'Friday' when 6 then 'Saturday' else 'Sunday'
    end                                                          as day_name,
    iso_dow in (6, 7)                                            as is_weekend
from attributes
