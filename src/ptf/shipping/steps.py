"""Pipeline step of the shipping domain; takes only the settings (CLI, app, later Airflow)."""

from ptf.core import warehouse
from ptf.core.settings import Settings
from ptf.shipping import portwatch, weather
from ptf.shipping.config import load_monitor_config
from ptf.shipping.reference import write_port_reference

CONFIG_FILE = "shipping.yaml"


def refresh(settings: Settings) -> None:
    """New PortWatch days (incremental), events and weather, then `dbt build -s tag:shipping`."""
    config = load_monitor_config(settings.config_dir / CONFIG_FILE)
    raw = settings.raw_dir
    port_names = {p.id: p.name for p in config.ports}

    portwatch.ingest_chokepoints(raw)
    portwatch.ingest_chokepoint_transits(raw, revision_days=config.revision_days)
    portwatch.ingest_ports_reference(raw, list(port_names))
    portwatch.ingest_port_activity(raw, list(port_names), revision_days=config.revision_days)
    portwatch.ingest_events(raw)
    if config.download_country_trade:
        portwatch.ingest_country_trade(raw, revision_days=config.revision_days)
    portwatch.ingest_port_links(raw, config.min_link_capacity)
    weather.ingest_weather(raw, list(port_names), config.weather)

    write_port_reference(config, raw)
    # The optional country trade models are built only when their raw data exist.
    has_country_trade = any(portwatch.daily_dir(raw, "country_trade_daily").glob("*.parquet"))
    args = ["build", "--select", "tag:shipping"]
    if has_country_trade:
        args += ["--vars", "{country_trade_enabled: true}"]
    warehouse.run_dbt(settings, args)
