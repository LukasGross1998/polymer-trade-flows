"""Data access for the app: load the warehouse marts, refresh them on request.

The app only reads the DuckDB warehouse (ADR-011) and calls pipeline functions; it computes
nothing itself. Tables that do not exist yet (e.g. market data before the first
`ptf market` run, or the optional country trade) are None, and the affected tab shows
a hint instead of failing.
"""

from dataclasses import dataclass
from functools import cached_property

import pandas as pd

from ptf.core.settings import Settings
from ptf.core.warehouse import read_tables, table_exists
from ptf.insights import view
from ptf.insights.config import SourcingConfig, load_sourcing_config
from ptf.markets import steps as markets_steps
from ptf.markets.config import MarketConfig, load_market_config
from ptf.model.config import ModelConfig, load_model_config
from ptf.model.distances import read_distance_table
from ptf.shipping import steps as shipping_steps
from ptf.shipping.config import MonitorConfig, load_monitor_config


@dataclass
class AppData:
    monitor_config: MonitorConfig
    market_config: MarketConfig
    sourcing_config: SourcingConfig
    model_config: ModelConfig
    transits: pd.DataFrame
    chokepoints: pd.DataFrame
    port_activity: pd.DataFrame | None = None
    ports: pd.DataFrame | None = None
    events: pd.DataFrame | None = None
    market: pd.DataFrame | None = None
    country_trade: pd.DataFrame | None = None
    port_links: pd.DataFrame | None = None
    import_sources: pd.DataFrame | None = None
    distances: pd.DataFrame | None = None  # sea routes with passages (raw layer, model)
    distances_closed: pd.DataFrame | None = None  # same with the Red Sea closed
    import_sources_by_product: pd.DataFrame | None = None
    trade_by_class: pd.DataFrame | None = None
    class_tree: pd.DataFrame | None = None
    products: pd.DataFrame | None = None
    eu_duty: pd.DataFrame | None = None
    weather: pd.DataFrame | None = None

    @property
    def latest_date(self) -> pd.Timestamp:
        return self.transits["date"].max()

    @cached_property
    def chokepoint_history(self) -> pd.DataFrame:
        """Daily monitor table of all chokepoints (computed once per loaded data)."""
        return view.chokepoint_history(self.transits, self.monitor_config)

    @cached_property
    def sourcing(self) -> view.SourcingView | None:
        """The buyer's import sources and chokepoint exposure; None without trade or routes."""
        if self.import_sources is None or self.distances is None:
            return None
        return view.sourcing_view(
            self.import_sources,
            self.distances,
            self.chokepoints,
            self.chokepoint_history,
            self.sourcing_config,
        )

    def grade_options(self) -> list[dict[str, str]]:
        """Dropdown options: all grades, then each PE grade (HS6) with its short name."""
        options = [{"label": "All polyethylene grades", "value": view.ALL_GRADES}]
        if self.products is not None:
            for row in self.products.sort_values("hs6").to_dict("records"):
                options.append({"label": f"{row['product']} ({row['hs6']})", "value": row["hs6"]})
        return options

    def sources(self, grade: str = view.ALL_GRADES) -> pd.DataFrame | None:
        """Import sources of one grade (or all), in the shape of mart_import_sources."""
        if self.import_sources_by_product is None:
            return self.import_sources if grade == view.ALL_GRADES else None
        return view.sources_for_grade(self.import_sources_by_product, grade)

    def sourcing_for(self, grade: str) -> view.SourcingView | None:
        """Sourcing view of one grade; the cached `sourcing` for all grades."""
        if grade == view.ALL_GRADES:
            return self.sourcing
        sources = self.sources(grade)
        if sources is None or sources.empty or self.distances is None:
            return None
        return view.sourcing_view(
            sources,
            self.distances,
            self.chokepoints,
            self.chokepoint_history,
            self.sourcing_config,
        )

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
    "import_sources": "marts.mart_import_sources",
    "import_sources_by_product": "marts.mart_import_sources_by_product",
    "trade_by_class": "marts.mart_trade_by_class",
    "class_tree": "reference.commodity_class_tree",
    "products": "marts.dim_product",
    "eu_duty": "marts.mart_eu_duty",
    "weather": "marts.mart_marine_weather",
}


def monitor_data_available(settings: Settings) -> bool:
    """Whether the warehouse holds the chokepoint mart the app cannot do without."""
    return table_exists(settings, APP_TABLES["transits"])


def load_app_data(settings: Settings) -> AppData:
    tables = read_tables(settings, APP_TABLES)
    return AppData(
        monitor_config=load_monitor_config(settings.config_dir / "shipping.yaml"),
        market_config=load_market_config(settings.config_dir / "markets.yaml"),
        sourcing_config=load_sourcing_config(settings.config_dir / "sourcing.yaml"),
        model_config=load_model_config(settings.config_dir / "model.yaml"),
        transits=require(tables["transits"], "mart_chokepoint_transits"),
        chokepoints=require(tables["chokepoints"], "dim_chokepoint"),
        port_activity=tables["port_activity"],
        ports=tables["ports"],
        events=tables["events"],
        market=tables["market"],
        country_trade=tables["country_trade"],
        port_links=tables["port_links"],
        import_sources=tables["import_sources"],
        import_sources_by_product=tables["import_sources_by_product"],
        trade_by_class=tables["trade_by_class"],
        class_tree=tables["class_tree"],
        products=tables["products"],
        eu_duty=tables["eu_duty"],
        weather=tables["weather"],
        distances=read_distance_table(settings.raw_dir),
        distances_closed=read_distance_table(settings.raw_dir, "red_sea_closed"),
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
        before = self.data.latest_date
        shipping_steps.refresh(self.settings)
        markets_steps.refresh(self.settings)
        self.data = load_app_data(self.settings)
        return int((self.data.latest_date - before).days)
