-- Extra-regional import shares of one year and importer region must add up to 1.
select year, importer_region, sum(share_extra) as total
from {{ ref('mart_import_sources') }}
where not is_intra_regional
group by year, importer_region
having abs(sum(share_extra) - 1) > 1e-9
