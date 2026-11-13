select region, region_name, port, port_lon, port_lat
from {{ source('reference', 'regions') }}
