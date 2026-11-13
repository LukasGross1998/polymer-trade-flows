select
    f.date, f.port_id, p.port,
    f.portcalls, f.portcalls_tanker, f.portcalls_container, f."import", f."export",
    f.fetched_at
from {{ ref('fct_port_activity') }} as f
join {{ ref('dim_port') }} as p using (port_id)
order by f.port_id, f.date
