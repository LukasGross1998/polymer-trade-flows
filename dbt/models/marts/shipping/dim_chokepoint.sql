select chokepoint_id, chokepoint, lat, lon
from {{ ref('stg_portwatch__chokepoints') }}
