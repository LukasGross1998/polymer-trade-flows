"""Data access for the app: load the clean tables, refresh them on request.

The app only reads files and calls pipeline functions; it computes nothing itself. Tables
that do not exist yet (e.g. market data before the first `pipeline market` run) are None,
and the affected tab shows a hint instead of failing.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ptf.config import Settings
from ptf.market_config import MarketConfig, load_market_config
from ptf.monitor.config import MonitorConfig, load_monitor_config


@dataclass
class AppData:
    monitor_config: MonitorConfig
    market_config: MarketConfig
    transits: pd.DataFrame
    chokepoints: pd.DataFrame
    port_activity: pd.DataFrame | None = None
    ports: pd.DataFrame | None = None
    events: pd.DataFrame | None = None
    market: pd.DataFrame | None = None

    @property
    def latest_date(self) -> pd.Timestamp:
        return self.transits["date"].max()

    def chokepoint_coordinates(self) -> pd.DataFrame:
        return self.chokepoints.rename(columns={"chokepoint_id": "location_id"})

    def port_coordinates(self) -> pd.DataFrame:
        return self.ports.rename(columns={"port_id": "location_id"})


def _optional(path: Path) -> pd.DataFrame | None:
    return pd.read_parquet(path) if path.exists() else None


def load_app_data(settings: Settings) -> AppData:
    clean = settings.clean_dir
    return AppData(
        monitor_config=load_monitor_config(settings.config_dir / "monitor.yaml"),
        market_config=load_market_config(settings.config_dir / "market_data.yaml"),
        transits=pd.read_parquet(clean / "chokepoint_transits.parquet"),
        chokepoints=pd.read_parquet(clean / "chokepoints.parquet"),
        port_activity=_optional(clean / "port_activity.parquet"),
        ports=_optional(clean / "ports.parquet"),
        events=_optional(clean / "events.parquet"),
        market=_optional(clean / "market_series.parquet"),
    )


class AppState:
    """Holds the currently loaded data; `refresh` downloads new data and reloads.

    One process-wide object is fine for a local single-user app.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.data = load_app_data(settings)

    def refresh(self) -> int:
        """Update PortWatch and market data; returns the number of new chokepoint days."""
        from ptf.pipeline import run_market, run_portwatch  # avoid an import cycle

        before = self.data.latest_date
        run_portwatch(self.settings)
        run_market(self.settings)
        self.data = load_app_data(self.settings)
        return int((self.data.latest_date - before).days)
