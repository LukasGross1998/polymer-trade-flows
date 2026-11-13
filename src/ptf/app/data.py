"""Data access for the app: load the warehouse marts, refresh them on request.

The app only reads the DuckDB warehouse (ADR-011) and calls pipeline functions; it computes
nothing itself. Tables that do not exist yet (e.g. market data before the first
`pipeline market` run, or the optional country trade) are None, and the affected tab shows
a hint instead of failing.
"""

from dataclasses import dataclass

import pandas as pd

from ptf.config import Settings
from ptf.market_config import MarketConfig, load_market_config
from ptf.monitor.config import MonitorConfig, load_monitor_config
from ptf.warehouse import read_tables


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
    country_trade: pd.DataFrame | None = None
    port_links: pd.DataFrame | None = None

    @property
    def latest_date(self) -> pd.Timestamp:
        return self.transits["date"].max()

    def chokepoint_coordinates(self) -> pd.DataFrame:
        return self.chokepoints.rename(columns={"chokepoint_id": "location_id"})

    def port_coordinates(self) -> pd.DataFrame:
        return require(self.ports, "ports").rename(columns={"port_id": "location_id"})


def require(table: pd.DataFrame | None, name: str) -> pd.DataFrame:
    """Return an optional table, or fail clearly if it is not loaded.

    Tabs only register their callbacks when their data exist, so this narrows the type for
    the type checker and turns a silent `None` into a readable error.
    """
    if table is None:
        raise RuntimeError(f"table {name!r} is not loaded; run the pipeline step that builds it")
    return table


# Key of AppData -> warehouse table.
APP_TABLES = {
    "transits": "marts.mart_chokepoint_transits",
    "chokepoints": "marts.dim_chokepoint",
    "port_activity": "marts.mart_port_activity",
    "ports": "marts.dim_port",
    "events": "marts.fct_disruption_events",
    "market": "marts.mart_market_series",
    "country_trade": "marts.mart_country_trade",
    "port_links": "marts.fct_port_links",
}


def load_app_data(settings: Settings) -> AppData:
    tables = read_tables(settings, APP_TABLES)
    return AppData(
        monitor_config=load_monitor_config(settings.config_dir / "monitor.yaml"),
        market_config=load_market_config(settings.config_dir / "market_data.yaml"),
        transits=require(tables["transits"], "mart_chokepoint_transits"),
        chokepoints=require(tables["chokepoints"], "dim_chokepoint"),
        port_activity=tables["port_activity"],
        ports=tables["ports"],
        events=tables["events"],
        market=tables["market"],
        country_trade=tables["country_trade"],
        port_links=tables["port_links"],
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
