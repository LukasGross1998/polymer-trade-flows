select
    event_id, event_type, event, alert_level, country, from_date, to_date, lat, lon,
    affected_ports, n_affected_ports, description
from {{ ref('stg_portwatch__events') }}
order by from_date desc
