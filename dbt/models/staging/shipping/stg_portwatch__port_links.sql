-- Port-to-port links of the newest snapshot; links from a port to itself are dropped.
select
    from_portid                 as from_port_id,
    from_portname               as from_port,
    from_country,
    from_lat,
    from_lon,
    to_portid                   as to_port_id,
    to_portname                 as to_port,
    to_country,
    to_lat,
    to_lon,
    average_transit_days        as transit_days,
    daily_capacity_at_risk      as daily_capacity
from {{ source('portwatch', 'port_links') }}
where from_portid <> to_portid
qualify fetched_at = max(fetched_at) over ()
