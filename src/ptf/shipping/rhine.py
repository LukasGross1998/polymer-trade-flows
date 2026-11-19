"""Rhine water level at Kaub from PEGELONLINE (WSV; spec 019).

Kaub is the bottleneck gauge of the Middle Rhine: when its level is low, barges to the plants
upstream (Ludwigshafen, Basel) can carry less. The REST API keeps only the last 31 days of
15-minute values, so every download is stored and a longer history builds up from the first
download on. The low-water flag uses the station's own characteristic values (GlW, the
"equivalent water level" for low water) and the WSV status – no thresholds of our own.
Licence: Datenlizenz Deutschland – Zero 2.0 (any use allowed); no key.

Raw layer per download: `rhine/levels/<time>.parquet` (station, timestamp, level_cm) and
`rhine/station/<time>.parquet` (characteristic values and the current WSV status).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/{station}/W"
LEVEL_COLUMNS = ["station", "timestamp", "level_cm", "fetched_at"]
STATION_COLUMNS = ["station", "kind", "shortname", "longname", "value", "fetched_at"]


def rhine_dir(raw_dir: Path) -> Path:
    return raw_dir / "rhine"


def levels_frame(
    station: str, answer: list[dict[str, object]], fetched_at: datetime
) -> pd.DataFrame:
    frame = pd.DataFrame(answer, columns=["timestamp", "value"])
    return pd.DataFrame(
        {
            "station": station,
            "timestamp": pd.to_datetime(frame["timestamp"], utc=True),
            "level_cm": frame["value"].astype(float),
            "fetched_at": pd.Timestamp(fetched_at),
        }
    )[LEVEL_COLUMNS]


def station_frame(station: str, answer: dict[str, Any], fetched_at: datetime) -> pd.DataFrame:
    """Characteristic values (GlW, MW, NW, …) and the current WSV status as rows."""
    rows = []
    for value in answer.get("characteristicValues") or []:
        rows.append(
            {
                "station": station,
                "kind": "characteristic",
                "shortname": value["shortname"],
                "longname": str(value.get("longname", "")).strip(),
                "value": str(value["value"]),
            }
        )
    current = answer.get("currentMeasurement") or {}
    for key in ("stateMnwMhw", "stateNswHsw"):
        if key in current:
            rows.append(
                {
                    "station": station,
                    "kind": "status",
                    "shortname": key,
                    "longname": "WSV status of the current level",
                    "value": str(current[key]),
                }
            )
    frame = pd.DataFrame(rows, columns=STATION_COLUMNS[:-1])
    frame["fetched_at"] = pd.Timestamp(fetched_at)
    return frame[STATION_COLUMNS]


def ingest_rhine(
    raw_dir: Path,
    station: str,
    days: int,
    session: requests.Session | None = None,
    today: datetime | None = None,
) -> tuple[Path, Path]:
    now = today or datetime.now(UTC)
    session = session or requests.Session()
    base = BASE.format(station=station)
    levels = session.get(f"{base}/measurements.json", params={"start": f"P{days}D"}, timeout=60)
    levels.raise_for_status()
    info = session.get(
        f"{base}.json",
        params={"includeCurrentMeasurement": "true", "includeCharacteristicValues": "true"},
        timeout=60,
    )
    info.raise_for_status()
    paths = []
    for name, frame in [
        ("levels", levels_frame(station, levels.json(), now)),
        ("station", station_frame(station, info.json(), now)),
    ]:
        path = rhine_dir(raw_dir) / name / f"{now:%Y%m%dT%H%M%S%f}.parquet"
        if path.exists():
            raise FileExistsError(f"raw files are never overwritten: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        paths.append(path)
    logger.info("Rhine level at %s: %s values", station, len(levels.json()))
    return paths[0], paths[1]


def ensure_raw_files(raw_dir: Path) -> None:
    """Empty raw files before the first download, so the dbt sources always resolve."""
    for name, columns in [("levels", LEVEL_COLUMNS), ("station", STATION_COLUMNS)]:
        folder = rhine_dir(raw_dir) / name
        if not any(folder.glob("*.parquet")):
            folder.mkdir(parents=True, exist_ok=True)
            empty = pd.DataFrame({c: pd.Series(dtype="string") for c in columns})
            empty["fetched_at"] = pd.to_datetime(empty["fetched_at"], utc=True)
            if "timestamp" in empty:
                empty["timestamp"] = pd.to_datetime(empty["timestamp"], utc=True)
                empty["level_cm"] = empty["level_cm"].astype("float64")
            empty.to_parquet(folder / "00000000T000000000000.parquet", index=False)
