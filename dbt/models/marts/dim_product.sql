select
    p.hs6,
    coalesce(s.short_name, p.description) as product,
    p.description
from {{ ref('stg_baci__products') }} as p
left join {{ ref('product_short_names') }} as s using (hs6)
