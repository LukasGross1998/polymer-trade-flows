-- Eurostat monthly price indices (spec 019): one row per series and month.
select cast(date as date) as date, cast(series_id as varchar) as series_id, cast(value as double) as value
from {{ source('eurostat', 'landing_eurostat') }}
