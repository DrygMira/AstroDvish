from __future__ import annotations

import logging

import swisseph as swe

from app.config import Settings
from app.services.ephemeris_downloader import DownloadReport, EphemerisDownloader

logger = logging.getLogger(__name__)

REQUIRED_EPHE_FILES: tuple[str, ...] = (
    "sepl_18.se1",
    "sepl_24.se1",
    "semo_18.se1",
    "semo_24.se1",
    "seas_18.se1",
    "seas_24.se1",
)


def bootstrap_ephemeris(settings: Settings) -> DownloadReport:
    downloader = EphemerisDownloader(
        ephe_path=settings.sweph_ephe_path,
        base_urls=settings.parsed_download_base_urls(),
        timeout_seconds=settings.sweph_download_timeout,
        retries=settings.sweph_download_retries,
    )
    report = downloader.ensure_files(
        required_files=REQUIRED_EPHE_FILES,
        auto_download=settings.sweph_auto_download,
    )

    swe.set_ephe_path(str(settings.sweph_ephe_path))
    logger.info("Swiss Ephemeris path initialized: %s", settings.sweph_ephe_path)
    return report
