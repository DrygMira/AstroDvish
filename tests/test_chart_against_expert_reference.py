from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models.request_models import ChartRequest
from app.services.ephemeris_service import EphemerisService
from app.services.zodiac_service import normalize_degree, resolve_sign


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "expert_reference_charts.json"


def _load_case(case_id: str) -> dict:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for case in payload.get("cases", []):
        if case.get("case_id") == case_id:
            return case
    raise AssertionError(f"Case not found in fixture: {case_id}")


def _to_utc_z(local_iso: str, timezone_name: str) -> str:
    local_dt = datetime.fromisoformat(local_iso).replace(tzinfo=ZoneInfo(timezone_name))
    return local_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _arcmin_diff(a: float, b: float) -> float:
    delta = abs(a - b)
    if delta > 180:
        delta = 360 - delta
    return delta * 60


def test_reference_ufa_inputs_and_angles_close_to_expert_reference() -> None:
    case = _load_case("ekaterina_ufa_1984_10_25")
    source = case["input"]
    expected_utc = _to_utc_z(source["datetime_local"], source["timezone_name"])

    payload = ChartRequest(
        datetime_utc=expected_utc,
        latitude=source["latitude"],
        longitude=source["longitude"],
        house_system=source["house_system"],
        zodiac_mode=source["zodiac_mode"],
        sidereal_mode=source["sidereal_mode"],
        aspect_orb_profile=source["aspect_orb_profile"],
    )
    chart = EphemerisService(ephe_path="ephe").calculate_chart(payload)

    assert payload.datetime_as_z() == "1984-10-25T09:28:30Z"
    assert chart.input.latitude == source["latitude"]
    assert chart.input.longitude == source["longitude"]
    assert chart.input.house_system == source["house_system"]
    assert chart.input.zodiac_mode.value == source["zodiac_mode"]
    assert chart.houses.cusps["1"] == chart.angles["asc"]
    assert chart.houses.cusps["10"] == chart.angles["mc"]

    expected_asc = case["reference"]["angles"]["asc"]["absolute_degree_0_360"]
    expected_mc = case["reference"]["angles"]["mc"]["absolute_degree_0_360"]
    tolerance_arcmin = float(case["tolerances"]["angles_target_arcmin"])

    asc_diff_arcmin = _arcmin_diff(chart.angles["asc"], expected_asc)
    mc_diff_arcmin = _arcmin_diff(chart.angles["mc"], expected_mc)

    asc_sign = resolve_sign(normalize_degree(chart.angles["asc"]))[1]
    mc_sign = resolve_sign(normalize_degree(chart.angles["mc"]))[1]

    assert asc_sign == case["reference"]["angles"]["asc"]["sign_name_en"]
    assert mc_sign == case["reference"]["angles"]["mc"]["sign_name_en"]
    assert asc_diff_arcmin <= tolerance_arcmin
    assert mc_diff_arcmin <= tolerance_arcmin


def test_reference_ufa_truncating_seconds_reproduces_asc_mc_shift() -> None:
    case = _load_case("ekaterina_ufa_1984_10_25")
    source = case["input"]
    service = EphemerisService(ephe_path="ephe")

    utc_with_seconds = _to_utc_z(source["datetime_local"], source["timezone_name"])
    utc_without_seconds = _to_utc_z(source["datetime_local"][:-2] + "00", source["timezone_name"])

    with_seconds = service.calculate_chart(
        ChartRequest(
            datetime_utc=utc_with_seconds,
            latitude=source["latitude"],
            longitude=source["longitude"],
            house_system=source["house_system"],
            zodiac_mode=source["zodiac_mode"],
            sidereal_mode=source["sidereal_mode"],
            aspect_orb_profile=source["aspect_orb_profile"],
        )
    )
    without_seconds = service.calculate_chart(
        ChartRequest(
            datetime_utc=utc_without_seconds,
            latitude=source["latitude"],
            longitude=source["longitude"],
            house_system=source["house_system"],
            zodiac_mode=source["zodiac_mode"],
            sidereal_mode=source["sidereal_mode"],
            aspect_orb_profile=source["aspect_orb_profile"],
        )
    )

    asc_shift_arcmin = _arcmin_diff(with_seconds.angles["asc"], without_seconds.angles["asc"])
    mc_shift_arcmin = _arcmin_diff(with_seconds.angles["mc"], without_seconds.angles["mc"])

    assert 6.0 <= asc_shift_arcmin <= 12.0
    assert 6.0 <= mc_shift_arcmin <= 12.0


def test_reference_ufa_planets_shift_less_than_one_arcmin_for_30_seconds() -> None:
    case = _load_case("ekaterina_ufa_1984_10_25")
    source = case["input"]
    max_ok_arcmin = float(case["tolerances"]["planets_ok_arcmin"])
    investigate_arcmin = float(case["tolerances"]["planets_investigate_arcmin"])
    service = EphemerisService(ephe_path="ephe")

    utc_with_seconds = _to_utc_z(source["datetime_local"], source["timezone_name"])
    utc_without_seconds = _to_utc_z(source["datetime_local"][:-2] + "00", source["timezone_name"])

    with_seconds = service.calculate_chart(
        ChartRequest(
            datetime_utc=utc_with_seconds,
            latitude=source["latitude"],
            longitude=source["longitude"],
            house_system=source["house_system"],
            zodiac_mode=source["zodiac_mode"],
            sidereal_mode=source["sidereal_mode"],
            aspect_orb_profile=source["aspect_orb_profile"],
        )
    )
    without_seconds = service.calculate_chart(
        ChartRequest(
            datetime_utc=utc_without_seconds,
            latitude=source["latitude"],
            longitude=source["longitude"],
            house_system=source["house_system"],
            zodiac_mode=source["zodiac_mode"],
            sidereal_mode=source["sidereal_mode"],
            aspect_orb_profile=source["aspect_orb_profile"],
        )
    )

    for object_name, object_data in with_seconds.objects.items():
        shifted = without_seconds.objects[object_name]
        diff_arcmin = _arcmin_diff(
            object_data.absolute_degree_0_360,
            shifted.absolute_degree_0_360,
        )
        assert diff_arcmin <= max_ok_arcmin
        assert diff_arcmin < investigate_arcmin


def test_reference_ufa_full_planet_and_cusp_reference_pending() -> None:
    case = _load_case("ekaterina_ufa_1984_10_25")
    if not case["reference"].get("objects") and not case["reference"].get("houses"):
        pytest.xfail("Full expert reference for planets and all cusps is not provided yet.")
