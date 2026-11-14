"""What does one tonne cost delivered to Europe from each supplier country? (spec 007)

landed = price + freight + duty, where
- price   = BACI unit value of the country's exports to the focus region (value / tonnes,
            FOB, USD/t), optionally scaled to today with a resin price index;
- freight = sourced freight rate for the sea distance, times a freight factor; without a
            sourced rate (spec 015) freight is unknown (NaN) and "landed" is price + duty;
- duty    = EU duty rate (TARIC / WITS) x customs value; the customs value is CIF (price +
            freight, insurance ignored), or the price alone while freight is unknown.

Combines trade (unit values), model (distances, freight) and markets (FX, resin index),
so it lives in the insights layer (ADR-014). Unit values average over all PE grades; part of
the differences between countries is the product mix, not the price.
"""

from datetime import date

import pandas as pd

from ptf.insights.config import Duty
from ptf.markets import indicators
from ptf.model.config import FreightAssumption

COMPONENTS = ["price", "freight", "duty"]


def unit_prices(sources: pd.DataFrame, focus_region: str, year: int) -> pd.DataFrame:
    """Extra-regional suppliers of `focus_region` in `year` with their FOB unit value."""
    rows = sources[
        (sources["importer_region"] == focus_region)
        & (sources["year"] == year)
        & ~sources["is_intra_regional"]
        & (sources["qty_t"] > 0)
    ]
    prices = rows.assign(price_usd_t=rows["value_usd"] / rows["qty_t"])
    columns = ["exporter_iso3", "exporter_name", "exporter_region", "qty_t", "price_usd_t"]
    return prices[columns].reset_index(drop=True)


def reference_price(sources: pd.DataFrame, focus_region: str, year: int) -> float | None:
    """Average unit value of trade within the focus region ("buy in Europe"), USD/t."""
    rows = sources[
        (sources["importer_region"] == focus_region)
        & (sources["year"] == year)
        & sources["is_intra_regional"]
    ]
    qty = rows["qty_t"].sum()
    return float(rows["value_usd"].sum() / qty) if qty > 0 else None


def price_factor(market: pd.DataFrame, index_id: str, base_year: int) -> float:
    """Latest value of a price index / its average in `base_year`; 1.0 if not computable."""
    one = indicators.series(market, index_id)
    base = one.loc[one["date"].dt.year == base_year, "value"]
    if one.empty or base.empty or base.mean() == 0:
        return 1.0
    return float(one["value"].iloc[-1] / base.mean())


def landed_cost(
    prices: pd.DataFrame,
    distances: pd.DataFrame,
    freight: FreightAssumption | None,
    duty: Duty,
    focus_region: str,
    usd_per_eur: float,
    freight_factor: float = 1.0,
    price_scale: float = 1.0,
    on: date | None = None,
) -> pd.DataFrame:
    """Price, freight, duty and landed cost per supplier, in USD/t and EUR/t, cheapest first.

    Suppliers without a sea distance to the focus region (rest of world) are left out.
    Without a sourced freight rate the freight columns are NaN and landed = price + duty.
    Duty preferences apply on date `on` (TARIC validity).
    """
    to_focus = distances.loc[
        distances["dest_region"] == focus_region, ["origin_region", "distance_nm"]
    ]
    if "route_key" not in prices.columns:  # one port per region (spec 014: or per country)
        prices = prices.assign(route_key=prices["exporter_region"])
    table = prices.merge(to_focus, left_on="route_key", right_on="origin_region", how="inner")
    table = table.drop(columns=["origin_region"])
    table["price_usd_t"] = table["price_usd_t"] * price_scale
    if freight is not None:
        table["freight_usd_t"] = table["distance_nm"].map(freight.cost_usd_t) * freight_factor
    else:
        table["freight_usd_t"] = float("nan")
    table["duty_pct"] = table["exporter_iso3"].map(lambda iso3: duty.rate_pct(iso3, on))
    customs_value = table["price_usd_t"] + table["freight_usd_t"].fillna(0.0)
    table["duty_usd_t"] = customs_value * table["duty_pct"] / 100
    table["landed_usd_t"] = customs_value + table["duty_usd_t"]
    for part in [*COMPONENTS, "landed"]:
        table[f"{part}_eur_t"] = table[f"{part}_usd_t"] / usd_per_eur
    return table.sort_values("landed_usd_t").reset_index(drop=True)


def weighted_landed(table: pd.DataFrame, region: str, column: str = "landed_eur_t") -> float | None:
    """Volume-weighted landed cost of the suppliers in one exporter region (countries with
    several ports count with their cheapest port)."""
    rows = table[table["exporter_region"] == region]
    rows = rows.sort_values(column).drop_duplicates("exporter_iso3")
    qty = rows["qty_t"].sum()
    return float((rows[column] * rows["qty_t"]).sum() / qty) if qty > 0 else None
