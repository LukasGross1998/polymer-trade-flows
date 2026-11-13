-- Monitored ports: short name and role from the configuration, location from PortWatch.
select c.port_id, c.port, p.country, p.lat, p.lon, c.role
from {{ ref('stg_reference__ports') }} as c
join {{ ref('stg_portwatch__ports') }} as p using (port_id)
