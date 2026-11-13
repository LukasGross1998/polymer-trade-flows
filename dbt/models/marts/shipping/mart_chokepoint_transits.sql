-- Transits with the chokepoint name: the table the monitor and the app read.
select
    f.date, f.chokepoint_id, d.chokepoint,
    f.n_total, f.n_container, f.n_tanker, f.n_dry_bulk, f.n_general_cargo, f.n_roro, f.n_cargo,
    f.capacity, f.capacity_container, f.capacity_tanker,
    f.fetched_at
from {{ ref('fct_chokepoint_transits') }} as f
join {{ ref('dim_chokepoint') }} as d using (chokepoint_id)
order by f.chokepoint_id, f.date
