"""Which origins can a European buyer actually use? (spec 016)

- *not sourceable*: EU TARIC lists an import control under sanctions for the country
  (`import_controls`, e.g. Iran, Russia), or the user blocks it (`sourceable.blocked`, e.g.
  company policy). Shown greyed out with the reason, never recommended.
- *minor*: less than `sourceable.min_volume_t` tonnes to the focus region in the latest year.
  Shown, but marked: one shipment can be a large part of such a flow.
"""

import pandas as pd

from ptf.insights.config import SourcingConfig


def classify(countries: pd.DataFrame, config: SourcingConfig) -> pd.DataFrame:
    """Per exporter country (exporter_iso3, qty_t): sourceable, minor and reason."""
    settings = config.sourceable
    rows = []
    for row in countries.drop_duplicates("exporter_iso3").to_dict("records"):
        iso3 = row["exporter_iso3"]
        control = config.import_controls.get(iso3)
        reason = ""
        if control is not None:
            reason = f"EU import control: {control.regulation} – check the conditions in TARIC"
        elif iso3 in settings.blocked:
            reason = f"blocked: {settings.blocked[iso3]}"
        rows.append(
            {
                "exporter_iso3": iso3,
                "sourceable": not reason,
                "minor": float(row["qty_t"]) < settings.min_volume_t,
                "sourceable_reason": reason,
            }
        )
    columns = ["exporter_iso3", "sourceable", "minor", "sourceable_reason"]
    return pd.DataFrame(rows, columns=columns)
