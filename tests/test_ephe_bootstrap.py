from __future__ import annotations

from app.bootstrap_ephe import bootstrap_ephemeris
from app.config import Settings
from app.services.ephemeris_downloader import EphemerisDownloader


def test_bootstrap_downloads_missing_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "app.bootstrap_ephe.REQUIRED_EPHE_FILES",
        ("sepl_20.se1", "semo_20.se1"),
    )

    def fake_download(self: EphemerisDownloader, filename: str) -> None:
        destination = self.ephe_path / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"dummy-ephemeris")

    monkeypatch.setattr(EphemerisDownloader, "_download_single_file", fake_download)

    settings = Settings(
        SWEPH_EPHE_PATH=tmp_path / "ephe",
        SWEPH_AUTO_DOWNLOAD=True,
        SWEPH_DOWNLOAD_BASE_URLS="https://example.test/ephe",
        SWEPH_DOWNLOAD_TIMEOUT=5,
        SWEPH_DOWNLOAD_RETRIES=1,
    )

    report = bootstrap_ephemeris(settings)
    assert sorted(report.downloaded_files) == ["semo_20.se1", "sepl_20.se1"]
    assert report.missing_files == []
    assert (tmp_path / "ephe" / "sepl_20.se1").exists()
    assert (tmp_path / "ephe" / "semo_20.se1").exists()


def test_downloader_is_idempotent(monkeypatch, tmp_path) -> None:
    required = ("sepl_20.se1",)
    call_count = {"downloads": 0}

    def fake_download(self: EphemerisDownloader, filename: str) -> None:
        call_count["downloads"] += 1
        target = self.ephe_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"dummy")

    monkeypatch.setattr(EphemerisDownloader, "_download_single_file", fake_download)
    downloader = EphemerisDownloader(
        ephe_path=tmp_path / "ephe",
        base_urls=["https://example.test/ephe"],
        timeout_seconds=5,
        retries=1,
    )

    first = downloader.ensure_files(required_files=required, auto_download=True)
    second = downloader.ensure_files(required_files=required, auto_download=True)

    assert first.downloaded_files == ["sepl_20.se1"]
    assert second.downloaded_files == []
    assert call_count["downloads"] == 1
