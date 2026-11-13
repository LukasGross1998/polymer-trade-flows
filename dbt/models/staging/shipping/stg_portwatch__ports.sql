-- PortWatch reference data of the downloaded ports (country, coordinates).
select portid as port_id, portname as portwatch_name, country, lat, lon
from {{ source('portwatch', 'ports') }}
