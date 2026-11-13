select
    date, chokepoint_id,
    n_total, n_container, n_tanker, n_dry_bulk, n_general_cargo, n_roro, n_cargo,
    capacity, capacity_container, capacity_tanker,
    fetched_at
from {{ ref('stg_portwatch__chokepoint_transits') }}
