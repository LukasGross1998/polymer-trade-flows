"""The Dash app without a browser: build it on fixture data and call the view function."""

import json
from pathlib import Path

import pandas as pd
import pytest
from test_ingest_comtrade import FakeResponse, FakeSession, no_sleep

from ptf.app.__main__ import create_app
from ptf.app.callbacks import update_views
from ptf.app.data import load_monitor_data
from ptf.clean.portwatch import clean_transits
from ptf.config import Settings
from ptf.ingest import portwatch

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Clean PortWatch tables from the 18-row fixture (Suez, Bab el-Mandeb, Cape)."""
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", config_dir=REPO_ROOT / "config")
    features = json.loads((FIXTURES / "portwatch_daily_sample.json").read_text())["features"]
    session = FakeSession([FakeResponse(200, {"features": features})])
    portwatch.ingest_chokepoint_transits(settings.raw_dir, session=session, sleep=no_sleep)

    settings.clean_dir.mkdir(parents=True)
    clean_transits(settings.raw_dir).to_parquet(settings.clean_dir / "chokepoint_transits.parquet")
    chokepoints = pd.DataFrame(
        {
            "chokepoint_id": ["chokepoint1", "chokepoint4", "chokepoint7"],
            "chokepoint": ["Suez Canal", "Bab el-Mandeb Strait", "Cape of Good Hope"],
            "lat": [30.6, 12.6, -34.4],
            "lon": [32.4, 43.3, 18.5],
        }
    )
    chokepoints.to_parquet(settings.clean_dir / "chokepoints.parquet")
    return settings


def test_update_views_returns_all_outputs(settings: Settings) -> None:
    data = load_monitor_data(settings)

    map_fig, tiles, series_fig, diversion_fig, freshness = update_views(
        data, "chokepoint4", "container", "90d"
    )

    assert len(map_fig.data[0].lon) == 3  # one marker per chokepoint
    assert len(tiles) == 4
    assert [t.name for t in series_fig.data][-1] == "7-day average"
    assert len(diversion_fig.data) == 3
    assert freshness.startswith("Data up to 08 Nov 2026")


def test_app_builds_with_layout_and_callbacks(settings: Settings) -> None:
    app = create_app(settings)

    layout_ids = {c.id for c in app.layout._traverse() if getattr(c, "id", None)}
    assert {"chokepoint", "vessel-type", "period", "map", "timeseries", "diversion"} <= layout_ids
    assert len(app.callback_map) == 3
