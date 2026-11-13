from pathlib import Path

import pytest
from pydantic import ValidationError

from ptf.core.regions import RegionConfig, load_regions

REPO_ROOT = Path(__file__).resolve().parents[1]


def _config(regions: dict) -> dict:
    return {"rest_of_world": "ROW", "regions": regions}


def _region(countries: list[str]) -> dict:
    return {"name": "x", "port": {"name": "p", "lon": 0.0, "lat": 0.0}, "reporters": countries}


def test_project_region_config_is_valid() -> None:
    config = load_regions(REPO_ROOT / "config" / "regions.yaml")

    assert 8 <= len(config.regions) <= 10
    assert 25 <= len(config.reporters()) <= 32
    assert config.region_of("DEU") == "EUR"
    assert config.region_of("ESP") == "EUR"  # member, not a reporter
    assert config.comtrade_aliases["S19"] == "TWN"


def test_unlisted_country_falls_into_rest_of_world() -> None:
    config = RegionConfig.model_validate(_config({"EUR": _region(["DEU"])}))

    assert config.region_of("DEU") == "EUR"
    assert config.region_of("NGA") == "ROW"


def test_members_belong_to_region_but_are_not_reporters() -> None:
    region = _region(["DEU"]) | {"members": ["AUT"]}
    config = RegionConfig.model_validate(_config({"EUR": region}))

    assert config.region_of("AUT") == "EUR"
    assert config.reporters() == ["DEU"]


def test_country_in_two_regions_is_rejected() -> None:
    with pytest.raises(ValidationError, match="DEU is listed in both"):
        RegionConfig.model_validate(
            _config({"A": _region(["DEU"]), "B": _region(["FRA"]) | {"members": ["DEU"]}})
        )


def test_invalid_country_code_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not an ISO3"):
        RegionConfig.model_validate(_config({"A": _region(["Germany"])}))
