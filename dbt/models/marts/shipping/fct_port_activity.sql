-- Only the configured ports (dim_port), even if more ports were downloaded.
select a.date, a.port_id, a.portcalls, a.portcalls_tanker, a.portcalls_container,
       a."import", a."export", a.fetched_at
from {{ ref('stg_portwatch__port_activity') }} as a
join {{ ref('dim_port') }} as p using (port_id)
