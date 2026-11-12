"""Data access for the app: load the clean PortWatch tables, refresh them on request.

The app only reads files and calls pipeline functions; it computes nothing itself.
"""

from dataclasses import dataclass

import pandas as pd

from ptf.config import Settings
from ptf.monitor.config import MonitorConfig, load_monitor_config


@dataclass
class MonitorData:
    transits: pd.DataFrame
    chokepoints: pd.DataFrame
    config: MonitorConfig

    @property
    def latest_date(self) -> pd.Timestamp:
        return self.transits["date"].max()


def load_monitor_data(settings: Settings) -> MonitorData:
    clean = settings.clean_dir
    return MonitorData(
        transits=pd.read_parquet(clean / "chokepoint_transits.parquet"),
        chokepoints=pd.read_parquet(clean / "chokepoints.parquet"),
        config=load_monitor_config(settings.config_dir / "monitor.yaml"),
    )


class AppState:
    """Holds the currently loaded data; `refresh` downloads new days and reloads.

    One process-wide object is fine for a local single-user app.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.data = load_monitor_data(settings)

    def refresh(self) -> int:
        """Fetch new PortWatch days, rebuild the clean tables; returns the number of new days."""
        from ptf.pipeline import run_portwatch  # imported here to avoid an import cycle

        before = self.data.latest_date
        run_portwatch(self.settings)
        self.data = load_monitor_data(self.settings)
        return int((self.data.latest_date - before).days)
