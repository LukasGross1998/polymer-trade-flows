select iso3, region, is_reporter
from {{ source('reference', 'country_region') }}
