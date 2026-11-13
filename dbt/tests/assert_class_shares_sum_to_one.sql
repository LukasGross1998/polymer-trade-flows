-- Shares of value and tonnes of one year must add up to 1, and no trade may be lost.
with totals as (
    select year, sum(value_usd) as value_usd from {{ ref('stg_baci__all_trade') }} group by year
)
select m.year
from {{ ref('mart_trade_by_class') }} as m
join totals as t on m.year = t.year
group by m.year, t.value_usd
having abs(sum(m.value_share) - 1) > 1e-9
    or abs(sum(m.qty_share) - 1) > 1e-9
    or abs(sum(m.value_usd) - t.value_usd) > 1e-3
