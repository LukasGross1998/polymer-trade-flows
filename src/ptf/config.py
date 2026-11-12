"""Central application settings.

Values are read, in order of precedence, from environment variables and from a
local `.env` file. Secrets such as API keys live only in `.env`, which is git-ignored.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the whole project."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # UN Comtrade API key. Optional so that tests and offline work need no key.
    # SecretStr hides the value in logs and reprs ("**********").
    comtrade_api_key: SecretStr | None = None

    # Root folder of the local data lake (raw -> clean -> model layers).
    data_dir: Path = Path("data")

    # Folder with the YAML files that hold all model assumptions (regions, pipeline settings).
    config_dir: Path = Path("config")

    # Folder for generated documentation such as the data-quality report.
    docs_dir: Path = Path("docs")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def clean_dir(self) -> Path:
        return self.data_dir / "clean"

    @property
    def model_dir(self) -> Path:
        return self.data_dir / "model"


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and then reused."""
    return Settings()
