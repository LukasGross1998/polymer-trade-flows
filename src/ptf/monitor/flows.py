"""Trade flows: the port-to-port network and countries' trade by cargo type.

- Port network (PortWatch snapshot): which ports are connected, how much vessel capacity
  travels between them per day and how long the voyage takes.
- Country trade (PortWatch daily estimates): imports and exports by vessel type, which
  stands for the cargo: tankers ~ oil and chemicals, dry bulk ~ ore, coal and grain,
  containers ~ manufactured goods (including bagged polyethylene), RoRo ~ vehicles.
"""

import pandas as pd

from ptf.clean.portwatch import CARGO_TYPES
from ptf.monitor.config import MonitorConfig
from ptf.monitor.metrics import latest_status, location_series, series_table


def top_links(
    links: pd.DataFrame,
    n: int = 100,
    port_id: str | None = None,
    direction: str = "outbound",
    international_only: bool = True,
) -> pd.DataFrame:
    """The `n` links with the largest daily capacity.

    With `port_id`, only links leaving (`outbound`) or reaching (`inbound`) that port.
    `international_only` drops links within one country, which otherwise dominate the list
    (short coastal and feeder services, e.g. Shanghai - Ningbo).
    """
    selected = links
    if port_id is not None:
        column = "from_port_id" if direction == "outbound" else "to_port_id"
        selected = selected[selected[column] == port_id]
    if international_only:
        selected = selected[selected["from_country"] != selected["to_country"]]
    return selected.nlargest(n, "daily_capacity").reset_index(drop=True)


def port_options(links: pd.DataFrame, n: int = 300) -> pd.DataFrame:
    """The `n` ports with the largest outbound capacity, for a dropdown: port_id, port, country."""
    outbound = links.groupby(["from_port_id", "from_port", "from_country"], as_index=False)[
        "daily_capacity"
    ].sum()
    outbound = outbound.nlargest(n, "daily_capacity").sort_values("from_port")
    return outbound.rename(
        columns={"from_port_id": "port_id", "from_port": "port", "from_country": "country"}
    ).reset_index(drop=True)


def cargo_mix(
    country_trade: pd.DataFrame, iso3: str, flow: str, window_days: int = 30
) -> pd.DataFrame:
    """Rolling daily average of one country's imports or exports by cargo type (t/day).

    Long format: date, cargo_type, value. A 30-day window smooths single ship arrivals,
    which dominate daily values for smaller countries.
    """
    country = country_trade[country_trade["iso3"] == iso3].sort_values("date")
    frames = []
    for cargo_type in CARGO_TYPES:
        values = country.set_index("date")[f"{flow}_{cargo_type}"]
        rolling = values.rolling(window_days, min_periods=window_days).mean().dropna()
        frames.append(
            pd.DataFrame({"date": rolling.index, "cargo_type": cargo_type, "value": rolling.values})
        )
    return pd.concat(frames, ignore_index=True)


def country_ranking(
    country_trade: pd.DataFrame,
    flow: str,
    cargo_type: str,
    config: MonitorConfig,
    n: int = 15,
) -> pd.DataFrame:
    """Largest importers or exporters of one cargo type, latest 7-day average vs. normal.

    Countries are just another kind of "location" for the monitor metrics.
    """
    series = location_series(country_trade, "iso3", "country", f"{flow}_{cargo_type}")
    status = latest_status(series_table(series, config))
    return status.nlargest(n, "rolling").reset_index(drop=True)
