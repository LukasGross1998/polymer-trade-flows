"""Shipping reference table for dbt: the ports configured for the monitor."""

from pathlib import Path

import pandas as pd

from ptf.core.warehouse import reference_dir
from ptf.shipping.config import MonitorConfig


def write_port_reference(config: MonitorConfig, raw_dir: Path) -> Path:
    """The ports configured for the monitor (PortWatch id, short name, role)."""
    path = reference_dir(raw_dir) / "ports.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"port_id": p.id, "port": p.name, "role": p.role} for p in config.ports]
    pd.DataFrame(rows, columns=["port_id", "port", "role"]).to_parquet(path, index=False)
    return path
