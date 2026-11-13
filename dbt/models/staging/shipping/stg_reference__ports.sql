-- Ports configured for the monitor (short name and role from config/shipping.yaml).
select port_id, port, role
from {{ source('reference', 'ports') }}
