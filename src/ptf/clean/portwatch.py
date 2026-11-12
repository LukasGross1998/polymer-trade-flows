"""Clean IMF PortWatch raw downloads into one daily transit table and a chokepoint table."""

from pathlib import Path

import pandas as pd

from ptf.ingest.portwatch import daily_dir

# Vessel-count columns of PortWatch and the names used in the app.
VESSEL_TYPES = {
    "total": "n_total",
    "container": "n_container",
    "tanker": "n_tanker",
    "dry_bulk": "n_dry_bulk",
    "general_cargo": "n_general_cargo",
    "roro": "n_roro",
}

TRANSIT_COLUMNS = [
    "date",
    "chokepoint_id",
    "chokepoint",
    *VESSEL_TYPES.values(),
    "n_cargo",
    "capacity",
    "capacity_container",
    "capacity_tanker",
    "fetched_at",
]


def clean_transits(raw_dir: Path) -> pd.DataFrame:
    """All raw downloads combined; per (date, chokepoint) the most recently fetched row wins."""
    files = sorted(daily_dir(raw_dir).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no PortWatch raw data in {daily_dir(raw_dir)}")
    raw = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    transits = raw.rename(columns={"portid": "chokepoint_id", "portname": "chokepoint"})
    transits["date"] = pd.to_datetime(transits["date"])
    transits = (
        transits.sort_values("fetched_at")
        .drop_duplicates(["date", "chokepoint_id"], keep="last")
        .sort_values(["chokepoint_id", "date"])
    )
    count_columns = [*VESSEL_TYPES.values(), "n_cargo"]
    transits[count_columns] = transits[count_columns].astype("int64")
    return transits[TRANSIT_COLUMNS].reset_index(drop=True)


def clean_chokepoints(raw_dir: Path) -> pd.DataFrame:
    """Chokepoint id, name and coordinates."""
    raw = pd.read_parquet(raw_dir / "portwatch" / "chokepoints.parquet")
    return raw.rename(columns={"portid": "chokepoint_id", "portname": "chokepoint"})[
        ["chokepoint_id", "chokepoint", "lat", "lon"]
    ].reset_index(drop=True)
