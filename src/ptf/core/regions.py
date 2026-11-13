"""Load and query the country-to-region mapping from `config/regions.yaml`.

pydantic models validate the YAML on load, so a typo in the config fails early with a clear
message instead of producing silently wrong regional totals later.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator, model_validator


class Port(BaseModel):
    """Representative seaport of a region, used for sea distances."""

    name: str
    lon: float
    lat: float


class Region(BaseModel):
    """A model region.

    `reporters` are queried from Comtrade; `members` are further countries that belong to the
    region but are not queried (their trade is seen through the reporters' reports).
    """

    name: str
    port: Port
    reporters: list[str]
    members: list[str] = []

    @field_validator("reporters", "members")
    @classmethod
    def countries_are_iso3(cls, countries: list[str]) -> list[str]:
        for iso3 in countries:
            if len(iso3) != 3 or not iso3.isupper():
                raise ValueError(f"not an ISO3 country code: {iso3!r}")
        return countries

    def countries(self) -> list[str]:
        return self.reporters + self.members


class RegionConfig(BaseModel):
    rest_of_world: str
    comtrade_aliases: dict[str, str] = {}
    regions: dict[str, Region]

    @model_validator(mode="after")
    def each_country_in_one_region(self) -> "RegionConfig":
        seen: dict[str, str] = {}
        for code, region in self.regions.items():
            for iso3 in region.countries():
                if iso3 in seen:
                    raise ValueError(f"{iso3} is listed in both {seen[iso3]} and {code}")
                seen[iso3] = code
        if self.rest_of_world in self.regions:
            raise ValueError(f"{self.rest_of_world} must not be defined as a normal region")
        return self

    def region_of(self, iso3: str) -> str:
        """Return the region code of a country; unlisted countries belong to rest of world."""
        for code, region in self.regions.items():
            if iso3 in region.countries():
                return code
        return self.rest_of_world

    def reporters(self) -> list[str]:
        """All countries queried from Comtrade, in config order."""
        return [iso3 for region in self.regions.values() for iso3 in region.reporters]


def load_regions(path: Path) -> RegionConfig:
    with path.open(encoding="utf-8") as f:
        return RegionConfig.model_validate(yaml.safe_load(f))
