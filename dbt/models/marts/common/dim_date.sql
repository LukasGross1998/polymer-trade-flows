-- Calendar days from var('calendar_start') to today, with ISO year and week (the monitor
-- compares each day with the same ISO week of the baseline years).
select
    cast(day as date)            as date,
    year(day)                    as year,
    month(day)                   as month,
    isoyear(day)                 as iso_year,
    least(week(day), 52)         as iso_week  -- week 53 folded into 52, as in ptf.monitor
from range(date '{{ var("calendar_start") }}', current_date + interval 1 day, interval 1 day) as t(day)
