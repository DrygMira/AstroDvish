from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.errors import EphemerisBootstrapError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DownloadReport:
    required_files: tuple[str, ...]
    found_files: list[str]
    downloaded_files: list[str]
    missing_files: list[str]


class EphemerisDownloader:
    def __init__(
        self,
        *,
        ephe_path: Path,
        base_urls: list[str],
        timeout_seconds: int,
        retries: int,
    ) -> None:
        self.ephe_path = ephe_path
        self.base_urls = [url.rstrip("/") for url in base_urls]
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def ensure_files(
        self,
        *,
        required_files: tuple[str, ...],
        auto_download: bool,
    ) -> DownloadReport:
        self.ephe_path.mkdir(parents=True, exist_ok=True)
        found_files = sorted(
            [name for name in required_files if (self.ephe_path / name).exists()]
        )
        missing_files = [name for name in required_files if name not in found_files]

        logger.info("Ephemeris path: %s", self.ephe_path)
        logger.info("Ephemeris files found: %s", found_files)
        if not missing_files:
            return DownloadReport(
                required_files=required_files,
                found_files=found_files,
                downloaded_files=[],
                missing_files=[],
            )

        logger.info("Ephemeris files missing: %s", missing_files)
        if not auto_download:
            logger.warning(
                "Auto-download is disabled; missing files remain unresolved: %s",
                missing_files,
            )
            return DownloadReport(
                required_files=required_files,
                found_files=found_files,
                downloaded_files=[],
                missing_files=missing_files,
            )

        downloaded_files: list[str] = []
        for filename in missing_files:
            self._download_single_file(filename)
            downloaded_files.append(filename)
            logger.info("Downloaded ephemeris file: %s", filename)

        unresolved = [
            name for name in required_files if not (self.ephe_path / name).exists()
        ]
        if unresolved:
            raise EphemerisBootstrapError(
                "Unable to download required Swiss Ephemeris files",
                details={"missing_files": unresolved},
            )

        return DownloadReport(
            required_files=required_files,
            found_files=found_files,
            downloaded_files=downloaded_files,
            missing_files=[],
        )

    def _download_single_file(self, filename: str) -> None:
        destination = self.ephe_path / filename
        if destination.exists():
            return

        if not self.base_urls:
            raise EphemerisBootstrapError(
                "No SWEPH_DOWNLOAD_BASE_URLS configured",
                details={"file": filename},
            )

        timeout = httpx.Timeout(self.timeout_seconds)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            errors: list[str] = []
            for base_url in self.base_urls:
                url = f"{base_url}/{filename}"
                for attempt in range(1, self.retries + 1):
                    try:
                        with client.stream("GET", url) as response:
                            if response.status_code != 200:
                                errors.append(
                                    f"{url} -> status {response.status_code}"
                                )
                                continue

                            temp_file = destination.with_suffix(
                                destination.suffix + ".tmp"
                            )
                            with temp_file.open("wb") as fp:
                                for chunk in response.iter_bytes():
                                    fp.write(chunk)
                            temp_file.replace(destination)
                            return
                    except httpx.HTTPError as exc:
                        errors.append(f"{url} attempt {attempt}: {exc}")

        raise EphemerisBootstrapError(
            "Failed to download ephemeris file",
            details={"file": filename, "errors": errors[-10:]},
        )

