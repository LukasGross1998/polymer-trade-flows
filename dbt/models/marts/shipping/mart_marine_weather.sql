-- Marine weather at chokepoints and monitored ports (spec 009): one row per location and day,
-- past days observed (model analysis) and the forecast from the latest download.
select
    w.date,
    w.location_id,
    w.location_type,
    coalesce(c.chokepoint, p.port, w.location_id) as location,
    w.wave_height_m,
    w.wind_gusts_kmh,
    w.wind_speed_kmh,
    w.date > cast(w.fetched_at as date)           as is_forecast,
    w.fetched_at
from {{ ref('stg_openmeteo__weather') }} as w
left join {{ ref('dim_chokepoint') }} as c on w.location_id = c.chokepoint_id
left join {{ ref('dim_port') }} as p on w.location_id = p.port_id
