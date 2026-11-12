"""Market indicators and overview summaries on small hand-checkable examples."""

import pandas as pd
import pytest

from ptf.market import indicators
from ptf.monitor.overview import active_events, disrupted_count, furthest_below_normal


def market(*rows: tuple[str, str, float]) -> pd.DataFrame:
    return pd.DataFrame([{"series_id": s, "date": pd.Timestamp(d), "value": v} for s, d, v in rows])


def test_latest_and_change_pct() -> None:
    data = market(("B", "2026-10-01", 80), ("B", "2026-10-20", 90), ("B", "2026-11-03", 100))

    assert indicators.latest(data, "B") == (pd.Timestamp("2026-11-03"), 100.0)
    # 30 days before 2026-11-03 is 2026-10-04: the last value on or before is 80.
    assert indicators.change_pct(data, "B", 30) == pytest.approx(25.0)
    assert indicators.latest(data, "missing") is None


def test_gas_spread_uses_monthly_means() -> None:
    data = market(
        ("DHHNGSP", "2026-09-01", 2.0),
        ("DHHNGSP", "2026-09-15", 4.0),  # September mean 3.0
        ("EU", "2026-09-01", 25.0),
    )

    spread = indicators.gas_spread(data, "EU")

    assert spread["value"].tolist() == [22.0]


def test_indexed_rebases_each_series_to_100() -> None:
    data = market(("A", "2026-01-01", 50), ("A", "2026-02-01", 75), ("B", "2026-01-15", 4))

    rebased = indicators.indexed(data, ["A", "B"], pd.Timestamp("2026-01-01"))

    assert rebased[rebased["series_id"] == "A"]["value"].tolist() == [100.0, 150.0]
    assert rebased[rebased["series_id"] == "B"]["value"].tolist() == [100.0]


def test_disrupted_locations_sorted_by_drop() -> None:
    status = pd.DataFrame(
        {
            "location": ["a", "b", "c"],
            "deviation_pct": [-40.0, -95.0, 10.0],
            "is_disrupted": [True, True, False],
        }
    )

    assert disrupted_count(status) == (2, 3)
    assert furthest_below_normal(status)["location"].tolist() == ["b", "a"]


def test_active_events_open_or_recent_and_severe() -> None:
    events = pd.DataFrame(
        {
            "event": ["open red", "old red", "recent orange", "open green", "future red"],
            "alert_level": ["RED", "RED", "ORANGE", "GREEN", "RED"],
            "from_date": pd.to_datetime(
                ["2026-03-01", "2025-01-01", "2026-10-20", "2026-10-01", "2026-12-01"]
            ),
            "to_date": pd.to_datetime([None, "2025-01-10", "2026-10-25", None, None]),
        }
    )

    active = active_events(events, as_of=pd.Timestamp("2026-11-08"))

    assert active["event"].tolist() == ["open red", "recent orange"]
