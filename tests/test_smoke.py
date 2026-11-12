"""Smoke tests: the package imports and settings behave as expected."""

from pathlib import Path

import pytest

import ptf
from ptf.config import Settings


def test_package_has_version() -> None:
    assert ptf.__version__ == "0.1.0"


def test_settings_load_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ignore any real .env and environment variables so the test is deterministic.
    monkeypatch.delenv("COMTRADE_API_KEY", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)

    settings = Settings(_env_file=None)

    assert settings.comtrade_api_key is None
    assert settings.data_dir == Path("data")
    assert settings.raw_dir == Path("data/raw")


def test_api_key_is_read_from_env_and_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMTRADE_API_KEY", "dummy-test-key")

    settings = Settings(_env_file=None)

    assert settings.comtrade_api_key is not None
    assert settings.comtrade_api_key.get_secret_value() == "dummy-test-key"
    # The secret must never show up when settings are printed or logged.
    assert "dummy-test-key" not in repr(settings)
