-- Daily port activity of all downloaded ports; the most recently fetched value per day wins.
select
    cast(date as date) as date,
    portid             as port_id,
    portcalls, portcalls_tanker, portcalls_container,
    "import", "export",
    fetched_at
from {{ source('portwatch', 'ports_daily') }}
qualify row_number() over (partition by date, portid order by fetched_at desc) = 1
