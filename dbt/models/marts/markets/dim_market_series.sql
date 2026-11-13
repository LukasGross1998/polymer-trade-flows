select series_id, name, unit, frequency, "group"
from {{ ref('stg_reference__market_series') }}
