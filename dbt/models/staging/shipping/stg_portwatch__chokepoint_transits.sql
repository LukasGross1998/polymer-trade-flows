-- Daily chokepoint transits; PortWatch revises recent days, so the most recently fetched
-- value per day and chokepoint wins.
select
    cast(date as date)       as date,
    portid                   as chokepoint_id,
    portname                 as chokepoint,
    n_total, n_container, n_tanker, n_dry_bulk, n_general_cargo, n_roro, n_cargo,
    capacity, capacity_container, capacity_tanker,
    fetched_at
from {{ source('portwatch', 'chokepoints_daily') }}
qualify row_number() over (partition by date, portid order by fetched_at desc) = 1
