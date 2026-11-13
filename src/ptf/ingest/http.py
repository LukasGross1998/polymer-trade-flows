"""Shared HTTP helper: GET JSON with retries on throttling and temporary server errors."""

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Status codes worth retrying: throttling and temporary server errors.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

Sleep = Callable[[float], None]


class QuotaExceededError(RuntimeError):
    """The daily request quota of the API is used up (HTTP 403 "Quota Exceeded").

    Retrying within the same day is pointless, so this is not retried. Cached files stay
    valid; rerun the ingest after the quota has been reset.
    """


def get_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any] | None = None,
    max_retries: int = 5,
    base_wait_seconds: float = 2.0,
    sleep: Sleep = time.sleep,
) -> dict[str, Any]:
    """GET a JSON document; on throttling or server errors wait 2, 4, 8, ... seconds and retry."""
    for attempt in range(max_retries + 1):
        response = session.get(url, params=params, timeout=60)
        if response.status_code == 403:
            raise QuotaExceededError(f"HTTP 403 for {url}: daily quota probably exceeded")
        if response.status_code not in RETRYABLE_STATUS:
            response.raise_for_status()  # other 4xx errors are bugs, not worth retrying
            return response.json()

        if attempt == max_retries:
            response.raise_for_status()
        wait = base_wait_seconds * 2**attempt
        logger.warning("HTTP %s for %s, retrying in %.0f s", response.status_code, url, wait)
        sleep(wait)

    raise AssertionError("unreachable")  # the loop either returns or raises
