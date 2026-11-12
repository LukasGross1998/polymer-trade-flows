"""Summary figures for the overview tab: what is disrupted right now?"""

import pandas as pd


def disrupted_count(status: pd.DataFrame) -> tuple[int, int]:
    """Number of flagged locations and number of locations in a latest-status table."""
    return int(status["is_disrupted"].sum()), len(status)


def furthest_below_normal(status: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The `n` flagged locations with the largest drop against normal."""
    flagged = status[status["is_disrupted"]]
    return flagged.sort_values("deviation_pct").head(n).reset_index(drop=True)


def active_events(events: pd.DataFrame, as_of: pd.Timestamp, recent_days: int = 30) -> pd.DataFrame:
    """Events still open (no end date) or ended within `recent_days` before `as_of`.

    Only orange and red alerts: green alerts are minor and would crowd the list.
    """
    still_open = events["to_date"].isna()
    recently_ended = events["to_date"] >= as_of - pd.Timedelta(days=recent_days)
    severe = events["alert_level"].isin(["ORANGE", "RED"])
    started = events["from_date"] <= as_of
    return events[(still_open | recently_ended) & severe & started].reset_index(drop=True)
