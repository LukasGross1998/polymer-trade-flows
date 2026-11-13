"""Trade-flow logic on small made-up networks and trade tables."""

import pandas as pd
import pytest

from ptf.monitor.config import MonitorConfig
from ptf.monitor.flows import cargo_mix, country_ranking, port_options, top_links
from ptf.monitor.vocabulary import CARGO_TYPES

CONFIG = MonitorConfig.model_validate(
    {
        "baseline_years": [2019],
        "rolling_window_days": 2,
        "disruption_threshold": 0.7,
        "min_baseline_per_day": 0,
        "red_sea": {"red_sea_route": "r", "cape_route": "c"},
        "revision_days": 14,
    }
)


def link(
    src: str, dst: str, src_country: str, dst_country: str, capacity: float, days: float = 10.0
) -> dict:
    return {
        "transit_days": days,
        "from_port_id": src,
        "from_port": src.upper(),
        "from_country": src_country,
        "to_port_id": dst,
        "to_port": dst.upper(),
        "to_country": dst_country,
        "daily_capacity": capacity,
    }


LINKS = pd.DataFrame(
    [
        link("sha", "nin", "China", "China", 900.0),  # coastal: largest, but domestic
        link("sha", "rtm", "China", "Netherlands", 300.0),
        link("jub", "sha", "Saudi Arabia", "China", 200.0),
        link("sha", "sgp", "China", "Singapore", 100.0),
        link("hkg", "szx", "Hong Kong", "China", 800.0, days=1.0),  # short feeder service
    ]
)


def test_top_links_keep_long_haul_by_default() -> None:
    # Domestic (sha-nin) and short international (hkg-szx, 1 day) links are dropped.
    assert top_links(LINKS, n=2)["to_port_id"].tolist() == ["rtm", "sha"]
    assert top_links(LINKS, n=1, long_haul_only=False)["to_port_id"].tolist() == ["nin"]


def test_top_links_for_one_port_by_direction() -> None:
    outbound = top_links(LINKS, port_id="sha", direction="outbound")
    inbound = top_links(LINKS, port_id="sha", direction="inbound")

    assert outbound["to_port_id"].tolist() == ["rtm", "sgp"]
    assert inbound["from_port_id"].tolist() == ["jub"]


def test_port_options_sorted_by_name() -> None:
    options = port_options(LINKS, n=2)  # the two largest exporters: sha (1,300), hkg (800)

    assert options["port"].tolist() == ["HKG", "SHA"]


def country_trade(iso3: str, start: str, exports_tanker: list[float]) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "date": pd.date_range(start, periods=len(exports_tanker)),
            "iso3": iso3,
            "country": iso3,
        }
    )
    for flow in ("import", "export"):
        for cargo in CARGO_TYPES:
            frame[f"{flow}_{cargo}"] = 0.0
    frame["export_tanker"] = exports_tanker
    return frame


def test_cargo_mix_is_rolling_mean_per_cargo_type() -> None:
    trade = country_trade("SAU", "2026-01-01", [10.0, 20.0, 30.0])

    mix = cargo_mix(trade, "SAU", "export", window_days=2)

    tanker = mix[mix["cargo_type"] == "tanker"]["value"].tolist()
    assert tanker == [15.0, 25.0]
    assert set(mix["cargo_type"]) == set(CARGO_TYPES)


def test_country_ranking_largest_first_with_deviation() -> None:
    trade = pd.concat(
        [
            country_trade("SAU", "2019-01-01", [100.0] * 30),
            country_trade("SAU", "2026-01-01", [10.0] * 3),  # far below normal
            country_trade("USA", "2019-01-01", [50.0] * 30),
            country_trade("USA", "2026-01-01", [60.0] * 3),
        ]
    )

    ranking = country_ranking(trade, "export", "tanker", CONFIG)

    assert ranking["location"].tolist() == ["USA", "SAU"]
    sau = ranking.set_index("location").loc["SAU"]
    assert sau["deviation_pct"] == pytest.approx(-90)
    assert sau["is_disrupted"]
