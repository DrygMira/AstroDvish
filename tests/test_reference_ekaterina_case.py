from __future__ import annotations

from app.models.request_models import ChartRequest
from app.services.ephemeris_service import EphemerisService


def test_ekaterina_reference_case_asc_mc_close() -> None:
    # Buston (former Chkalovsk, Tajikistan) reference coordinates from geocoder:
    # latitude=40.23417, longitude=69.69481
    # Local 1978-03-19 22:59:45 at UTC+05 => UTC 1978-03-19 17:59:45Z
    service = EphemerisService(ephe_path="ephe")
    payload = ChartRequest(
        datetime_utc="1978-03-19T17:59:45Z",
        latitude=40.23417,
        longitude=69.69481,
        house_system="P",
        zodiac_mode="tropical",
        sidereal_mode=None,
        aspect_orb_profile="avestan",
    )
    chart = service.calculate_chart(payload)

    expected_asc = 232.596111  # 22°35′46″ Scorpio
    expected_mc = 154.704167  # 04°42′15″ Virgo

    assert abs(chart.angles["asc"] - expected_asc) <= 0.2
    assert abs(chart.angles["mc"] - expected_mc) <= 0.2
    assert chart.houses.cusps["1"] == chart.angles["asc"]
    assert chart.houses.cusps["10"] == chart.angles["mc"]
