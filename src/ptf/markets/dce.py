"""Daily LLDPE futures price from the Dalian Commodity Exchange via AKShare (spec 011).

AKShare is an optional dependency (`uv sync --extra asia`, ADR-015). It reads the main
contract's daily prices from Sina Finance, an unofficial source ("for academic research",
interfaces "may be removed", by AKShare's own statement). Therefore:
- AKShare is imported inside the function, so this module loads without it;
- a missing AKShare or a failing download only logs a message and returns None, so the
  market step and the app keep working;
- every download is its own raw file, never overwritten; `write_dce_landing` keeps the
  newest value per day for dbt and always writes a file (empty before the first download).
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# AKShare's Chinese column names -> ours.
COLUMNS = {
    "日期": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "持仓量": "open_interest",
    "动态结算价": "settle",
}
LANDING_COLUMNS = ["date", "open", "high", "low", "close", "volume", "open_interest", "settle"]

Fetch = Callable[[str, str, str], pd.DataFrame]


def dce_dir(raw_dir: Path) -> Path:
    return raw_dir / "dce"


def akshare_fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
    """AKShare's Sina main-contract history; raises ImportError without the `asia` extra."""
    import akshare  # optional dependency (extra "asia"), imported only when used

    return akshare.futures_main_sina(symbol=symbol, start_date=start, end_date=end)


def tidy(frame: pd.DataFrame) -> pd.DataFrame:
    """Rename the Chinese columns and type the values; one row per trading day."""
    table = frame.rename(columns=COLUMNS)[LANDING_COLUMNS].copy()
    table["date"] = pd.to_datetime(table["date"])
    for column in LANDING_COLUMNS[1:]:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table.sort_values("date").reset_index(drop=True)


def ingest_dce(
    raw_dir: Path,
    symbol: str,
    start_date: date,
    fetch: Fetch | None = None,
    today: datetime | None = None,
) -> Path | None:
    """Download the daily history into a new raw file; None if AKShare or the source fails."""
    now = today or datetime.now(UTC)
    try:
        frame = (fetch or akshare_fetch)(symbol, f"{start_date:%Y%m%d}", f"{now:%Y%m%d}")
    except ImportError:
        logger.info("AKShare not installed (uv sync --extra asia): DCE price skipped")
        return None
    except Exception as error:  # an unofficial source: never let it stop the market step
        logger.warning("DCE download failed, keeping the stored data: %s", error)
        return None
    table = tidy(frame)
    if table.empty:
        logger.warning("DCE download returned no rows")
        return None
    path = dce_dir(raw_dir) / f"{now:%Y%m%dT%H%M%S%f}.parquet"
    if path.exists():
        raise FileExistsError(f"raw files are never overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    table.assign(fetched_at=pd.Timestamp(now)).to_parquet(path, index=False)
    logger.info("DCE %s: %s days -> %s", symbol, len(table), path)
    return path


def write_dce_landing(raw_dir: Path) -> Path:
    """Newest value per day over all downloads in `dce/landing_dce.parquet` (maybe empty)."""
    files = sorted(
        p for p in dce_dir(raw_dir).glob("*.parquet") if not p.name.startswith("landing")
    )
    if files:
        table = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
        table = table.sort_values("fetched_at").drop_duplicates("date", keep="last")
        landing = table[LANDING_COLUMNS].sort_values("date").reset_index(drop=True)
    else:
        landing = pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ns]"),
                **{c: pd.Series(dtype=float) for c in LANDING_COLUMNS[1:]},
            }
        )
    path = dce_dir(raw_dir) / "landing_dce.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    landing.to_parquet(path, index=False)
    return path
