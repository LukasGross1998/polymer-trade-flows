-- Disruption events from the newest download (the full list is downloaded each time).
-- PortWatch stores dates as epoch milliseconds.
select
    eventid                                         as event_id,
    eventtype                                       as event_type,
    eventname                                       as event,
    alertlevel                                      as alert_level,
    country,
    cast(epoch_ms(fromdate) as date)                as from_date,
    cast(epoch_ms(cast(todate as bigint)) as date)  as to_date,
    lat,
    long                                            as lon,
    affectedports                                   as affected_ports,
    n_affectedports                                 as n_affected_ports,
    htmldescription                                 as description
from {{ source('portwatch', 'events') }}
qualify fetched_at = max(fetched_at) over ()
