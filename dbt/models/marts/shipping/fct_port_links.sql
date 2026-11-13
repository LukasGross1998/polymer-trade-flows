select
    from_port_id, from_port, from_country, from_lat, from_lon,
    to_port_id, to_port, to_country, to_lat, to_lon,
    transit_days, daily_capacity
from {{ ref('stg_portwatch__port_links') }}
order by daily_capacity desc
