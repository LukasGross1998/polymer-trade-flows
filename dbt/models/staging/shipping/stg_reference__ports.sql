-- Ports configured for the monitor (short name and role from config/monitor.yaml).
select port_id, port, role
from {{ source('reference', 'ports') }}
