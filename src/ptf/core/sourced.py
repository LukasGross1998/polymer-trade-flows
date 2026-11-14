"""A value about the real world together with where it comes from (spec 015).

Rule: every number in `config/` that states a fact (a cost, a duration, a rate, a location)
is written as

    fixed_usd_t: {value: 40, source: "Drewry WCI, Shanghai-Rotterdam", url: "https://…",
                  read: 2026-11-14}

Settings (choices of the user, such as traffic-light thresholds) stay plain numbers; the
value register `docs/value_register.md` says which keys are settings. A fact without
source, url and read date does not load.
"""

from datetime import date

from pydantic import BaseModel, Field


class Sourced(BaseModel):
    """A sourced number: the value, its publisher/document, a link and the date it was read."""

    value: float
    source: str = Field(min_length=3)
    url: str = Field(pattern=r"^https?://")
    read: date
    note: str = ""

    def __float__(self) -> float:
        return float(self.value)

    def label(self) -> str:
        """Short citation for the UI, e.g. 'Drewry WCI, read 14 Nov 2026'."""
        return f"{self.source}, read {self.read:%d %b %Y}"


class SourcedTable(BaseModel):
    """Several sourced numbers from the same table, e.g. time in port per country."""

    values: dict[str, float]
    source: str = Field(min_length=3)
    url: str = Field(pattern=r"^https?://")
    read: date
    note: str = ""

    def get(self, key: str) -> float | None:
        """The value for `key`, or None when the source has none (shown as "n/a")."""
        value = self.values.get(key)
        return None if value is None else float(value)

    def label(self) -> str:
        return f"{self.source}, read {self.read:%d %b %Y}"


class SourcedRate(Sourced):
    """A sourced rate with the validity period given by the source (e.g. a tariff preference)."""

    valid_from: date | None = None
    valid_to: date | None = None
