select
    cast(code as varchar)     as hs6,
    trim(description)         as description
from {{ source('baci', 'landing_product_codes') }}
