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


# Port metrics of PortWatch: calls (vessels per day) and estimated trade volumes (t per day).
PORT_METRICS = {
    "portcalls": "port calls, all vessels",
    "portcalls_tanker": "port calls, tankers",
    "portcalls_container": "port calls, container ships",
    "import": "import volume (t)",
    "export": "export volume (t)",
}
PORT_COLUMNS = ["date", "port_id", "port", *PORT_METRICS, "fetched_at"]
EVENT_COLUMNS = [
    "event_id",
    "event_type",
    "event",
    "alert_level",
    "country",
    "from_date",
    "to_date",
    "lat",
    "lon",
    "affected_ports",
    "n_affected_ports",
    "description",
]
EVENT_TYPES = {
    "DR": "drought",
    "EQ": "earthquake",
    "FL": "flood",
    "OT": "other (e.g. conflict)",
    "TC": "tropical cyclone",
    "VO": "volcano",
    "WF": "wildfire",
}


def _latest_per_day(raw: pd.DataFrame, id_column: str) -> pd.DataFrame:
    raw = raw.assign(date=pd.to_datetime(raw["date"]))
    return (
        raw.sort_values("fetched_at")
        .drop_duplicates(["date", id_column], keep="last")
        .sort_values([id_column, "date"])
    )


def clean_port_activity(raw_dir: Path, port_names: dict[str, str]) -> pd.DataFrame:
    """Daily activity of the configured ports; `port_names` maps PortWatch id -> short name."""
    files = sorted(daily_dir(raw_dir, "ports_daily").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no PortWatch port data in {daily_dir(raw_dir, 'ports_daily')}")
    raw = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    raw = raw[raw["portid"].isin(port_names)].rename(columns={"portid": "port_id"})
    ports = _latest_per_day(raw, "port_id")
    ports["port"] = ports["port_id"].map(port_names)
    return ports[PORT_COLUMNS].reset_index(drop=True)


def clean_ports(raw_dir: Path, port_names: dict[str, str]) -> pd.DataFrame:
    raw = pd.read_parquet(raw_dir / "portwatch" / "ports.parquet")
    raw = raw[raw["portid"].isin(port_names)].rename(columns={"portid": "port_id"})
    raw["port"] = raw["port_id"].map(port_names)
    return raw[["port_id", "port", "country", "lat", "lon"]].reset_index(drop=True)


def clean_events(raw_dir: Path) -> pd.DataFrame:
    """Disruption events from the newest download; dates from epoch milliseconds."""
    files = sorted((raw_dir / "portwatch" / "events").glob("*.parquet"))
    if not files:
        raise FileNotFoundError("no PortWatch event data")
    raw = pd.read_parquet(files[-1])
    events = raw.rename(
        columns={
            "eventid": "event_id",
            "eventtype": "event_type",
            "eventname": "event",
            "alertlevel": "alert_level",
            "fromdate": "from_date",
            "todate": "to_date",
            "long": "lon",
            "affectedports": "affected_ports",
            "n_affectedports": "n_affected_ports",
            "htmldescription": "description",
        }
    )
    for column in ["from_date", "to_date"]:
        events[column] = pd.to_datetime(events[column], unit="ms").dt.normalize()
    return events.sort_values("from_date", ascending=False)[EVENT_COLUMNS].reset_index(drop=True)


CARGO_TYPES = {
    "tanker": "tankers (crude oil, products, chemicals, LNG/LPG)",
    "dry_bulk": "dry bulk (ore, coal, grain)",
    "container": "containers (manufactured goods, also bagged polymers)",
    "general_cargo": "general cargo",
    "roro": "RoRo (vehicles)",
}
COUNTRY_TRADE_COLUMNS = [
    "date",
    "iso3",
    "country",
    "import",
    "export",
    *[f"{flow}_{kind}" for flow in ("import", "export") for kind in CARGO_TYPES],
    "fetched_at",
]
PORT_LINK_COLUMNS = [
    "from_port_id",
    "from_port",
    "from_country",
    "from_lat",
    "from_lon",
    "to_port_id",
    "to_port",
    "to_country",
    "to_lat",
    "to_lon",
    "transit_days",
    "daily_capacity",
]


def clean_country_trade(raw_dir: Path) -> pd.DataFrame:
    """Daily estimated imports and exports per country, total and by vessel type (t/day)."""
    files = sorted(daily_dir(raw_dir, "country_trade_daily").glob("*.parquet"))
    if not files:
        raise FileNotFoundError("no PortWatch country trade data")
    raw = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    raw = raw.rename(columns={"ISO3": "iso3"}).dropna(subset=["iso3"])
    trade = _latest_per_day(raw, "iso3")
    return trade[COUNTRY_TRADE_COLUMNS].reset_index(drop=True)


def clean_port_links(raw_dir: Path) -> pd.DataFrame:
    """Port-to-port links of the newest snapshot: transit days and daily vessel capacity.

    `daily_capacity` is PortWatch's "daily capacity at risk": the vessel capacity (deadweight
    tonnes) that travels from the origin to the destination port per day on average.
    """
    files = sorted((raw_dir / "portwatch" / "port_links").glob("*.parquet"))
    if not files:
        raise FileNotFoundError("no PortWatch port network data")
    raw = pd.read_parquet(files[-1])
    links = raw.rename(
        columns={
            "from_portid": "from_port_id",
            "from_portname": "from_port",
            "to_portid": "to_port_id",
            "to_portname": "to_port",
            "average_transit_days": "transit_days",
            "daily_capacity_at_risk": "daily_capacity",
        }
    )
    links = links[links["from_port_id"] != links["to_port_id"]]
    return links.sort_values("daily_capacity", ascending=False)[PORT_LINK_COLUMNS].reset_index(
        drop=True
    )


def clean_chokepoints(raw_dir: Path) -> pd.DataFrame:
    """Chokepoint id, name and coordinates."""
    raw = pd.read_parquet(raw_dir / "portwatch" / "chokepoints.parquet")
    return raw.rename(columns={"portid": "chokepoint_id", "portname": "chokepoint"})[
        ["chokepoint_id", "chokepoint", "lat", "lon"]
    ].reset_index(drop=True)
