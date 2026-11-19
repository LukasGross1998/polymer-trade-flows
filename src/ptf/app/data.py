"""Data access for the app: load the warehouse marts, refresh them on request.

The app only reads the DuckDB warehouse (ADR-011) and calls pipeline functions; it computes
nothing itself. Tables that do not exist yet (e.g. market data before the first
`ptf market` run, or the optional country trade) are None, and the affected tab shows
a hint instead of failing.
"""

from dataclasses import dataclass, field
from functools import cached_property

import pandas as pd

from ptf.core.settings import Settings
from ptf.core.warehouse import read_tables, table_exists, warehouse_path
from ptf.insights import relevance, view
from ptf.insights.config import SourcingConfig, load_sourcing_config
from ptf.insights.scenario import ALL_OPEN, LIVE, Scenario
from ptf.insights.scenario import options as scenario_options
from ptf.markets import steps as markets_steps
from ptf.markets.config import MarketConfig, load_market_config
from ptf.model.config import ModelConfig, load_model_config
from ptf.model.distances import country_route_key, read_distance_table, with_combinations
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
    variant_distances: dict[str, pd.DataFrame] = field(default_factory=dict)  # detour variants
    import_sources_by_product: pd.DataFrame | None = None
    bilateral: pd.DataFrame | None = None  # PE trade per exporter and importer country
    eu_imports: pd.DataFrame | None = None  # Comext monthly EU imports (spec 019)
    rhine: pd.DataFrame | None = None  # daily Rhine level at Kaub (spec 019)
    trade_by_class: pd.DataFrame | None = None
    class_tree: pd.DataFrame | None = None
    products: pd.DataFrame | None = None
    eu_duty: pd.DataFrame | None = None
    weather: pd.DataFrame | None = None
    dce_quote: pd.DataFrame | None = None
    updated_at: pd.Timestamp | None = None  # last warehouse build (file time), spec 013
    _sourcing_cache: dict[tuple[str, str], view.SourcingView | None] = field(
        default_factory=dict, repr=False
    )

    @property
    def latest_date(self) -> pd.Timestamp:
        return self.transits["date"].max()

    @cached_property
    def chokepoint_history(self) -> pd.DataFrame:
        """Daily monitor table of all chokepoints (computed once per loaded data)."""
        return view.chokepoint_history(self.transits, self.monitor_config)

    @cached_property
    def route_tables(self) -> view.RouteTables | None:
        """Distance tables of all routes open, the detour variants and the country ports."""
        if self.distances is None:
            return None
        keys = {
            iso3: [country_route_key(iso3, p.name) for p in ports]
            for iso3, ports in self.model_config.country_ports().items()
        }
        return view.RouteTables(self.distances, self.variant_distances, keys)

    def scenario(self, key: str = LIVE) -> Scenario:
        """The route scenario `key` (spec 014); live status from the latest monitor data."""
        return view.resolve_scenario(key, self.chokepoint_history, self.sourcing_config)

    def scenario_options(self) -> list[dict[str, str]]:
        return scenario_options(self.sourcing_config.scenarios)

    @cached_property
    def sourcing(self) -> view.SourcingView | None:
        """The buyer's import sources and exposure in the live scenario; None without data."""
        return self.sourcing_for(view.ALL_GRADES, LIVE)

    @cached_property
    def relevance(self) -> relevance.Relevance | None:
        """What matters for the focus region's buyer (spec 013); None without sourcing data."""
        open_routes = self.sourcing_for(view.ALL_GRADES, ALL_OPEN.key)
        if open_routes is None:
            return None
        return relevance.build(
            open_routes.routes,
            self.sourcing_config.focus_region,
            self.monitor_config.ports,
            self.sourcing_config.relevance,
        )

    @cached_property
    def chokepoint_dependency(self) -> pd.DataFrame | None:
        """Share of the focus region's imports per chokepoint and its detour days (spec 014)."""
        open_routes = self.sourcing_for(view.ALL_GRADES, ALL_OPEN.key)
        if open_routes is None or self.distances is None:
            return None
        return relevance.chokepoint_dependency(
            open_routes.routes,
            {"base": self.distances, **self.variant_distances},
            self.sourcing_config.chokepoint_detours,
            self.sourcing_config.focus_region,
            self.sourcing_config.lead_time.speed,
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

    def sourcing_for(self, grade: str, scenario_key: str = LIVE) -> view.SourcingView | None:
        """Sourcing view of one grade (or all) in a route scenario; computed once each."""
        key = (grade, scenario_key)
        if key not in self._sourcing_cache:
            sources = self.sources(grade)
            tables = self.route_tables
            if sources is None or sources.empty or tables is None:
                self._sourcing_cache[key] = None
            else:
                scenario = ALL_OPEN if scenario_key == ALL_OPEN.key else self.scenario(scenario_key)
                self._sourcing_cache[key] = view.sourcing_view(
                    sources, tables, self.chokepoints, scenario, self.sourcing_config
                )
        return self._sourcing_cache[key]

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
    "bilateral": "marts.mart_bilateral_trade",
    "eu_imports": "marts.mart_eu_imports_monthly",
    "rhine": "marts.mart_rhine_level",
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
    "dce_quote": "marts.mart_dce_quote",
}


def monitor_data_available(settings: Settings) -> bool:
    """Whether the warehouse holds the chokepoint mart the app cannot do without."""
    return table_exists(settings, APP_TABLES["transits"])


def read_variants(settings: Settings, config: ModelConfig) -> dict[str, pd.DataFrame]:
    """Every ingested detour variant and combination (spec 014); missing ones are skipped."""
    names = with_combinations({k: v.restrictions for k, v in config.route_variants.items()})
    tables = {name: read_distance_table(settings.raw_dir, name) for name in names}
    return {name: table for name, table in tables.items() if table is not None}


def load_app_data(settings: Settings) -> AppData:
    tables = read_tables(settings, APP_TABLES)
    model_config = load_model_config(settings.config_dir / "model.yaml")
    path = warehouse_path(settings)
    updated_at = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC") if path.exists() else None
    return AppData(
        monitor_config=load_monitor_config(settings.config_dir / "shipping.yaml"),
        market_config=load_market_config(settings.config_dir / "markets.yaml"),
        sourcing_config=load_sourcing_config(settings.config_dir / "sourcing.yaml"),
        model_config=model_config,
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
        bilateral=tables["bilateral"],
        eu_imports=tables["eu_imports"],
        rhine=tables["rhine"],
        trade_by_class=tables["trade_by_class"],
        class_tree=tables["class_tree"],
        products=tables["products"],
        eu_duty=tables["eu_duty"],
        weather=tables["weather"],
        dce_quote=tables["dce_quote"],
        updated_at=updated_at,
        distances=read_distance_table(settings.raw_dir),
        variant_distances=read_variants(settings, model_config),
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
