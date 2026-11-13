select series_id, name, unit, frequency, "group"
from {{ source('reference', 'market_series') }}
