"""Marine weather at the chokepoints and monitored ports (Open-Meteo, no key; spec 009).

Two requests per refresh, each for all locations at once (Open-Meteo accepts lists of
coordinates):
- marine API: daily maximum wave height (m); points on land have no waves (null);
- forecast API: daily maximum wind gusts and wind speed at 10 m (km/h).
Each covers the past days and a forecast. Every download is its own raw file, never
overwritten; dbt keeps the latest download per location and day.

Storm warnings compare the daily maxima with thresholds from `config/shipping.yaml`.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from ptf.shipping.config import WeatherConfig

logger = logging.getLogger(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_VARIABLES = {"wave_height_max": "wave_height_m"}
WIND_VARIABLES = {"wind_gusts_10m_max": "wind_gusts_kmh", "wind_speed_10m_max": "wind_speed_kmh"}

GREEN, AMBER, RED = "green", "amber", "red"


def weather_dir(raw_dir: Path) -> Path:
    return raw_dir / "weather"


def weather_locations(raw_dir: Path, port_ids: list[str]) -> pd.DataFrame:
    """Chokepoints and configured ports with coordinates, from the PortWatch raw files.

    Columns: location_id, location_type ("chokepoint" or "port"), lat, lon.
    """
    frames = []
    chokepoints = raw_dir / "portwatch" / "chokepoints.parquet"
    if chokepoints.exists():
        frames.append(pd.read_parquet(chokepoints).assign(location_type="chokepoint"))
    ports = raw_dir / "portwatch" / "ports.parquet"
    if ports.exists():
        table = pd.read_parquet(ports)
        frames.append(table[table["portid"].isin(port_ids)].assign(location_type="port"))
    if not frames:
        return pd.DataFrame(columns=["location_id", "location_type", "lat", "lon"])
    rows = pd.concat(frames, ignore_index=True).rename(columns={"portid": "location_id"})
    return rows[["location_id", "location_type", "lat", "lon"]].reset_index(drop=True)


def _daily(
    session: requests.Session,
    url: str,
    locations: pd.DataFrame,
    variables: dict[str, str],
    config: WeatherConfig,
) -> pd.DataFrame:
    """One Open-Meteo request for all locations; long table location_id, date, variables."""
    params: dict[str, str | int] = {
        "latitude": ",".join(f"{v:.4f}" for v in locations["lat"]),
        "longitude": ",".join(f"{v:.4f}" for v in locations["lon"]),
        "daily": ",".join(variables),
        "past_days": config.past_days,
        "forecast_days": config.forecast_days,
        "timezone": "UTC",
    }
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()
    payload: Any = response.json()
    answers = payload if isinstance(payload, list) else [payload]  # one location: a dict
    frames = []
    for location_id, answer in zip(locations["location_id"], answers, strict=True):
        daily = answer.get("daily", {})
        frame = pd.DataFrame({"date": pd.to_datetime(daily.get("time", []))})
        for source, column in variables.items():
            frame[column] = pd.to_numeric(pd.Series(daily.get(source, [None] * len(frame))))
        frames.append(frame.assign(location_id=location_id))
    return pd.concat(frames, ignore_index=True)


def fetch_weather(
    session: requests.Session, locations: pd.DataFrame, config: WeatherConfig
) -> pd.DataFrame:
    """Daily wave height, gusts and wind for all locations: past days and forecast."""
    marine = _daily(session, MARINE_URL, locations, MARINE_VARIABLES, config)
    wind = _daily(session, FORECAST_URL, locations, WIND_VARIABLES, config)
    merged = marine.merge(wind, on=["location_id", "date"], how="outer")
    types = locations.set_index("location_id")["location_type"]
    merged["location_type"] = merged["location_id"].map(types)
    columns = [
        "location_id",
        "location_type",
        "date",
        "wave_height_m",
        "wind_gusts_kmh",
        "wind_speed_kmh",
    ]
    return merged[columns].sort_values(["location_id", "date"]).reset_index(drop=True)


def ingest_weather(
    raw_dir: Path,
    port_ids: list[str],
    config: WeatherConfig,
    session: requests.Session | None = None,
) -> Path | None:
    """Download the weather of all locations into a new raw file; None without locations."""
    locations = weather_locations(raw_dir, port_ids)
    if locations.empty:
        logger.warning("no chokepoint or port coordinates yet: weather skipped")
        return None
    now = datetime.now(UTC)
    table = fetch_weather(session or requests.Session(), locations, config)
    path = weather_dir(raw_dir) / f"{now:%Y%m%dT%H%M%S%f}.parquet"
    if path.exists():
        raise FileExistsError(f"raw files are never overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    table.assign(fetched_at=pd.Timestamp(now)).to_parquet(path, index=False)
    logger.info("weather for %s locations written to %s", len(locations), path)
    return path


def storm_level(wave_height_m: float | None, gusts_kmh: float | None, config: WeatherConfig) -> str:
    """'red', 'amber' or 'green': the worse of waves and gusts; unknown values count as calm."""

    def one(value: float | None, amber: float, red: float) -> int:
        if value is None or pd.isna(value):
            return 0
        return 2 if value >= red else 1 if value >= amber else 0

    worst = max(
        one(wave_height_m, config.waves_m.amber, config.waves_m.red),
        one(gusts_kmh, config.gusts_kmh.amber, config.gusts_kmh.red),
    )
    return [GREEN, AMBER, RED][worst]


def storm_warnings(
    weather: pd.DataFrame, as_of: pd.Timestamp, config: WeatherConfig
) -> pd.DataFrame:
    """Forecast days from `as_of` on with an amber or red storm level, worst first."""
    future = weather[weather["date"] >= as_of].copy()
    future["level"] = [
        storm_level(w, g, config)
        for w, g in zip(future["wave_height_m"], future["wind_gusts_kmh"], strict=True)
    ]
    warnings = future[future["level"] != GREEN]
    order = {RED: 0, AMBER: 1}
    return warnings.sort_values(
        ["level", "date"], key=lambda c: c.map(order) if c.name == "level" else c
    ).reset_index(drop=True)
