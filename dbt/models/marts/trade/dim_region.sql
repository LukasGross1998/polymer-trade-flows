-- Model regions from config/regions.yaml plus the rest-of-world region.
select region, region_name, port, port_lon, port_lat
from {{ ref('stg_reference__regions') }}
union all
select 'ROW', 'Rest of world', null, null, null
