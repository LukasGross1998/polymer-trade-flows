"""Trade reference tables for dbt: regions, country -> region, code aliases."""

from pathlib import Path

import pandas as pd

from ptf.core.regions import RegionConfig
from ptf.core.warehouse import reference_dir


def write_reference_tables(regions: RegionConfig, raw_dir: Path) -> list[Path]:
    """Regions, country -> region mapping and Comtrade/BACI code aliases as Parquet."""
    folder = reference_dir(raw_dir)
    folder.mkdir(parents=True, exist_ok=True)
    region_rows = [
        {
            "region": code,
            "region_name": region.name,
            "port": region.port.name,
            "port_lon": region.port.lon,
            "port_lat": region.port.lat,
        }
        for code, region in regions.regions.items()
    ]
    country_rows = [
        {"iso3": iso3, "region": code, "is_reporter": iso3 in region.reporters}
        for code, region in regions.regions.items()
        for iso3 in region.countries()
    ]
    alias_rows = [{"code": code, "iso3": iso3} for code, iso3 in regions.comtrade_aliases.items()]
    paths = [
        folder / "regions.parquet",
        folder / "country_region.parquet",
        folder / "country_aliases.parquet",
    ]
    pd.DataFrame(region_rows).to_parquet(paths[0], index=False)
    pd.DataFrame(country_rows).to_parquet(paths[1], index=False)
    pd.DataFrame(alias_rows, columns=["code", "iso3"]).to_parquet(paths[2], index=False)
    return paths
