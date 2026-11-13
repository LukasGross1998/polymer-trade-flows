-- World trade per year and commodity class (spec 008): value, tonnes and their shares.
-- Each code gets the class of its longest matching prefix in the seed, else "Other goods".
with matches as (
    select
        t.year,
        t.code,
        c.class,
        row_number() over (
            partition by t.year, t.code order by length(c.prefix) desc
        ) as rank
    from {{ ref('stg_baci__all_trade') }} as t
    left join {{ ref('commodity_classes') }} as c on starts_with(t.code, c.prefix)
),

classified as (
    select
        t.year,
        coalesce(m.class, 'Other goods') as class,
        t.value_usd,
        coalesce(t.qty_t, 0)             as qty_t,
        t.value_usd_without_qty
    from {{ ref('stg_baci__all_trade') }} as t
    join matches as m on t.year = m.year and t.code = m.code and m.rank = 1
),

by_class as (
    select
        year,
        class,
        sum(value_usd)             as value_usd,
        sum(qty_t)                 as qty_t,
        sum(value_usd_without_qty) as value_usd_without_qty
    from classified
    group by year, class
)

select
    b.year,
    b.class,
    tree.parent,
    tree.sort_order,
    b.value_usd,
    b.qty_t,
    b.value_usd_without_qty,
    b.value_usd / sum(b.value_usd) over (partition by b.year) as value_share,
    b.qty_t / sum(b.qty_t) over (partition by b.year)         as qty_share
from by_class as b
join {{ ref('commodity_class_tree') }} as tree on b.class = tree.class
