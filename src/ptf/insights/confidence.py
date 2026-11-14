"""How far can a supplier's price be trusted? Price ranges, product mix and confidence (spec 016).

BACI gives one annual unit value (value / tonnes) per country and HS6 grade. A country's
average over all grades mixes cheap and expensive grades, so two countries can differ only
because they sell a different mix. Three numbers make that visible:

- price range: lowest to highest grade price among the grades with at least
  `min_grade_share` % of the country's tonnes;
- mix-adjusted price: the country's grade prices weighted with the *focus region's* import
  mix of grades – the same basket for every origin (weights renormalised over the grades the
  country sells);
- mix effect: unit value − mix-adjusted price, in USD/t and in % of the unit value.

Confidence (high / medium / low) is the lowest of three checks with user thresholds:
volume, size of the mix effect and age of the data.
"""

import pandas as pd

from ptf.insights.config import ConfidenceSettings

HIGH, MEDIUM, LOW = "high", "medium", "low"
ORDER = [HIGH, MEDIUM, LOW]


def grade_prices(by_product: pd.DataFrame, focus_region: str, year: int) -> pd.DataFrame:
    """Extra-regional imports of the focus region per exporter and grade with unit value."""
    rows = by_product[
        (by_product["importer_region"] == focus_region)
        & (by_product["year"] == year)
        & ~by_product["is_intra_regional"]
        & (by_product["qty_t"] > 0)
    ]
    return rows.assign(price_usd_t=rows["value_usd"] / rows["qty_t"])


def import_mix(prices: pd.DataFrame) -> pd.Series:
    """Share of each grade in the focus region's extra-regional imports (sums to 1)."""
    tonnes = prices.groupby("hs6")["qty_t"].sum()
    return tonnes / tonnes.sum()


def price_ranges(
    by_product: pd.DataFrame, focus_region: str, year: int, min_grade_share: float
) -> pd.DataFrame:
    """Per exporter: price_low, price_high, unit_value, mix_adjusted, mix_effect (USD/t) and
    mix_effect_pct."""
    prices = grade_prices(by_product, focus_region, year)
    mix = import_mix(prices)
    rows = []
    for iso3, group in prices.groupby("exporter_iso3"):
        total = group["qty_t"].sum()
        main = group[group["qty_t"] / total * 100 >= min_grade_share]
        unit_value = float(group["value_usd"].sum() / total)
        weights = mix.reindex(group["hs6"]).to_numpy()
        adjusted = float((group["price_usd_t"].to_numpy() * weights).sum() / weights.sum())
        rows.append(
            {
                "exporter_iso3": iso3,
                "price_low": float(main["price_usd_t"].min()),
                "price_high": float(main["price_usd_t"].max()),
                "unit_value": unit_value,
                "mix_adjusted": adjusted,
                "mix_effect": unit_value - adjusted,
                "mix_effect_pct": (unit_value - adjusted) / unit_value * 100,
            }
        )
    columns = [
        "exporter_iso3",
        "price_low",
        "price_high",
        "unit_value",
        "mix_adjusted",
        "mix_effect",
        "mix_effect_pct",
    ]
    return pd.DataFrame(rows, columns=columns)


def level(
    qty_t: float,
    mix_effect_pct: float | None,
    data_age_years: int,
    min_volume_t: float,
    settings: ConfidenceSettings,
) -> tuple[str, str]:
    """(level, reason): the lowest of volume, product mix and data age."""
    checks: list[tuple[str, str]] = []
    if qty_t < min_volume_t:
        checks.append((LOW, f"small volume ({qty_t / 1e3:,.1f} kt)"))
    if mix_effect_pct is not None and not pd.isna(mix_effect_pct):
        size = abs(mix_effect_pct)
        if size >= settings.mix_low_pct:
            checks.append((LOW, f"product mix moves the price by {mix_effect_pct:+.0f} %"))
        elif size >= settings.mix_medium_pct:
            checks.append((MEDIUM, f"product mix moves the price by {mix_effect_pct:+.0f} %"))
    if data_age_years >= settings.age_low_years:
        checks.append((LOW, f"data {data_age_years} years old"))
    elif data_age_years >= settings.age_medium_years:
        checks.append((MEDIUM, f"data {data_age_years} years old"))
    if not checks:
        return HIGH, "enough volume, small product-mix effect, recent data"
    worst = max(ORDER.index(c[0]) for c in checks)
    reasons = [text for lvl, text in checks if ORDER.index(lvl) == worst]
    return ORDER[worst], "; ".join(reasons)


def europe_difference(
    prices: pd.DataFrame,
    reference: pd.DataFrame,
    iso3: str,
    duty_pct: float,
    min_grade_share: float,
) -> tuple[float, float] | None:
    """Lowest and highest difference, over the country's main grades, between its grade price
    plus EU duty and the price of the same grade within the focus region (USD/t).

    `reference` is the intra-regional unit value per grade (hs6, price_usd_t)."""
    own = prices[prices["exporter_iso3"] == iso3]
    if own.empty:
        return None
    own = own[own["qty_t"] / own["qty_t"].sum() * 100 >= min_grade_share]
    merged = own.merge(reference, on="hs6", suffixes=("", "_ref"))
    if merged.empty:
        return None
    diff = merged["price_usd_t"] * (1 + duty_pct / 100) - merged["price_usd_t_ref"]
    return float(diff.min()), float(diff.max())


def reference_grade_prices(by_product: pd.DataFrame, focus_region: str, year: int) -> pd.DataFrame:
    """Unit value of trade within the focus region per grade (hs6, price_usd_t)."""
    rows = by_product[
        (by_product["importer_region"] == focus_region)
        & (by_product["year"] == year)
        & by_product["is_intra_regional"]
    ]
    grouped = rows.groupby("hs6", as_index=False).agg(
        qty_t=("qty_t", "sum"), value_usd=("value_usd", "sum")
    )
    grouped = grouped[grouped["qty_t"] > 0]
    return grouped.assign(price_usd_t=grouped["value_usd"] / grouped["qty_t"])[
        ["hs6", "price_usd_t"]
    ]
