-- Daily Rhine water level per station (PEGELONLINE, spec 019) with the station's own
-- characteristic values from the newest download: GlW (equivalent low water level) and MW
-- (mean water level). below_glw = the daily minimum is under GlW.
with latest_station as (
    select *
    from {{ source('rhine', 'station') }}
    where station is not null
    qualify row_number() over (partition by station, kind, shortname order by fetched_at desc) = 1
),

characteristic as (
    select
        station,
        max(case when shortname = 'GlW' then cast(value as double) end) as glw_cm,
        max(case when shortname = 'MW' then cast(value as double) end)  as mw_cm,
        max(case when shortname = 'stateMnwMhw' then value end)         as wsv_status
    from latest_station
    group by station
),

daily as (
    select
        station,
        cast(timezone('Europe/Berlin', measured_at) as date) as date,
        avg(level_cm) as level_cm,
        min(level_cm) as min_level_cm
    from {{ ref('stg_pegelonline__levels') }}
    group by all
)

select
    d.station,
    d.date,
    d.level_cm,
    d.min_level_cm,
    c.glw_cm,
    c.mw_cm,
    c.wsv_status,
    d.min_level_cm < c.glw_cm as below_glw
from daily as d
left join characteristic as c using (station)
