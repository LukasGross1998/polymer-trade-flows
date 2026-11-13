"""Smoke tests: the package imports and settings behave as expected."""

import tomllib
from pathlib import Path

import pytest

import ptf
from ptf.core.settings import Settings


def test_package_version_comes_from_pyproject() -> None:
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())

    assert ptf.__version__ == pyproject["project"]["version"]


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


def test_app_and_dbt_settings_default_to_local_use(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_HOST", "APP_PORT", "DBT_PROJECT_DIR"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert (settings.app_host, settings.app_port) == ("127.0.0.1", 8050)
    assert (settings.dbt_project_dir / "dbt_project.yml").exists()  # the repository's dbt/


def test_container_overrides_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("DBT_PROJECT_DIR", "/app/dbt")

    settings = Settings(_env_file=None)

    assert (settings.app_host, settings.app_port) == ("0.0.0.0", 9000)
    assert settings.dbt_project_dir == Path("/app/dbt")
