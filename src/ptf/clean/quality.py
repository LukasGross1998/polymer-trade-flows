"""Quality rule 1: unit values (USD per tonne) and robust outlier flags.

A unit value far away from the typical polyethylene price almost always means a wrong weight
(e.g. kg reported as tonnes) rather than a real price. We flag such rows with a *robust*
z-score: median and MAD (median absolute deviation) are not pulled away by the outliers
themselves, unlike mean and standard deviation. Working on log(unit value) makes "10x too
high" and "10x too low" equally far from the centre.
"""

import numpy as np
import pandas as pd

# Scales the MAD so it equals the standard deviation for normally distributed data.
MAD_TO_STD = 1.4826


def add_unit_values(reports: pd.DataFrame) -> pd.DataFrame:
    """Add `unit_value_usd_t`; NaN where quantity or value is missing or zero."""
    usable = (reports["qty_t"] > 0) & (reports["value_usd"] > 0)
    unit_value = (reports["value_usd"] / reports["qty_t"]).where(usable)
    return reports.assign(unit_value_usd_t=unit_value)


def flag_unit_value_outliers(reports: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Add `uv_robust_z` and `is_uv_outlier` per year and flow.

    Grouping by flow keeps CIF-valued imports and FOB-valued exports apart.
    Rows without a unit value are never flagged.
    """
    log_uv = np.log(reports["unit_value_usd_t"])
    groups = [reports["year"], reports["flow"]]
    median = log_uv.groupby(groups).transform("median")
    mad = (log_uv - median).abs().groupby(groups).transform("median") * MAD_TO_STD

    robust_z = (log_uv - median) / mad.replace(0.0, np.nan)
    return reports.assign(
        uv_robust_z=robust_z,
        is_uv_outlier=(robust_z.abs() > threshold).fillna(False),
    )
