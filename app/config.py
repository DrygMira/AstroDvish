from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="astro-ephemeris-service", alias="APP_NAME")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8013, alias="APP_PORT")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")

    sweph_ephe_path: Path = Field(default=Path("/opt/ephe"), alias="SWEPH_EPHE_PATH")
    sweph_auto_download: bool = Field(default=True, alias="SWEPH_AUTO_DOWNLOAD")
    sweph_download_timeout: int = Field(default=120, alias="SWEPH_DOWNLOAD_TIMEOUT")
    sweph_download_retries: int = Field(default=2, alias="SWEPH_DOWNLOAD_RETRIES")
    sweph_download_base_urls: str = Field(
        default="https://www.astro.com/ftp/swisseph/ephe,https://github.com/aloistr/swisseph/raw/master/ephe",
        alias="SWEPH_DOWNLOAD_BASE_URLS",
    )

    def parsed_download_base_urls(self) -> list[str]:
        return [
            item.strip()
            for item in self.sweph_download_base_urls.split(",")
            if item.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
