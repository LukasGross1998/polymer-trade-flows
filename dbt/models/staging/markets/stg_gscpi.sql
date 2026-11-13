select 'GSCPI' as series_id, cast(date as date) as date, cast(value as double) as value
from {{ source('gscpi', 'landing_gscpi') }}
