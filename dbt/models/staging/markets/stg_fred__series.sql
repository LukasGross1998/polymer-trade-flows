-- FRED observations from the newest download of each series; days without a value dropped.
with files as (
    select
        regexp_extract(filename, 'fred/([^/]+)/[^/]+\.csv$', 1) as series_id,
        regexp_extract(filename, '([^/]+)\.csv$', 1)            as download_stamp,
        cast(observation_date as date) as observation_date,
        cast(value as double)          as value
    from {{ source('fred', 'series_csv') }}
)

select series_id, observation_date as date, value
from files
where value is not null
qualify download_stamp = max(download_stamp) over (partition by series_id)
