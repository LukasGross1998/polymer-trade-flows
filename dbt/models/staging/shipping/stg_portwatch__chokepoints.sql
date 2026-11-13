select portid as chokepoint_id, portname as chokepoint, lat, lon
from {{ source('portwatch', 'chokepoints') }}
