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


def _absolute_from_sign_dms(value: str) -> float:
    sign_map = {
        "Aries": 0,
        "Taurus": 30,
        "Gemini": 60,
        "Cancer": 90,
        "Leo": 120,
        "Virgo": 150,
        "Libra": 180,
        "Scorpio": 210,
        "Sagittarius": 240,
        "Capricorn": 270,
        "Aquarius": 300,
        "Pisces": 330,
    }
    cleaned = value.strip().replace(" R", "").replace(" D", "").replace(" S", "")
    sign_name, rest = cleaned.split(" ", 1)
    degrees_part, rest = rest.split("°", 1)
    minutes_part, rest = rest.split("'", 1)
    seconds_part = rest.split('"', 1)[0]
    sign_offset = sign_map[sign_name]
    degrees = float(degrees_part)
    minutes = float(minutes_part)
    seconds = float(seconds_part)
    return sign_offset + degrees + minutes / 60 + seconds / 3600


def _to_decimal_from_dms_coord(value: str) -> float:
    cleaned = value.strip().upper()
    for mark in ("″", '"'):
        cleaned = cleaned.replace(mark, "")
    cleaned = cleaned.replace("′", "'")
    degrees_part, rest = cleaned.split("°", 1)
    minutes_part, rest = rest.split("'", 1)
    seconds_token, hemisphere = rest.strip().split(" ", 1)
    degrees = float(degrees_part)
    minutes = float(minutes_part)
    seconds = float(seconds_token)
    decimal = abs(degrees) + minutes / 60 + seconds / 3600
    if hemisphere in {"S", "W"}:
        decimal *= -1
    return decimal


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


def test_radix_reference_ufa_uses_dms_coordinates_and_keeps_seconds() -> None:
    case = _load_case("ufa_1984_10_25_142830_radix")
    source = case["input"]
    latitude = _to_decimal_from_dms_coord(source["latitude_dms"])
    longitude = _to_decimal_from_dms_coord(source["longitude_dms"])
    expected_utc = _to_utc_z(source["datetime_local"], source["timezone_name"])

    payload = ChartRequest(
        datetime_utc=expected_utc,
        latitude=latitude,
        longitude=longitude,
        house_system=source["house_system"],
        zodiac_mode=source["zodiac_mode"],
        sidereal_mode=source["sidereal_mode"],
        aspect_orb_profile=source["aspect_orb_profile"],
    )
    chart = EphemerisService(ephe_path="ephe").calculate_chart(payload)

    assert payload.datetime_as_z() == "1984-10-25T09:28:30Z"
    assert abs(chart.input.latitude - latitude) < 1e-6
    assert abs(chart.input.longitude - longitude) < 1e-6
    assert chart.houses.cusps["1"] == chart.angles["asc"]
    assert chart.houses.cusps["10"] == chart.angles["mc"]


def test_radix_reference_ufa_angles_and_cusps_within_target_tolerance() -> None:
    case = _load_case("ufa_1984_10_25_142830_radix")
    source = case["input"]
    tolerance_arcmin = float(case["tolerances"]["angles_target_arcmin"])
    payload = ChartRequest(
        datetime_utc=_to_utc_z(source["datetime_local"], source["timezone_name"]),
        latitude=source["latitude"],
        longitude=source["longitude"],
        house_system=source["house_system"],
        zodiac_mode=source["zodiac_mode"],
        sidereal_mode=source["sidereal_mode"],
        aspect_orb_profile=source["aspect_orb_profile"],
    )
    chart = EphemerisService(ephe_path="ephe").calculate_chart(payload)

    expected_asc = _absolute_from_sign_dms(case["reference"]["angles"]["asc"])
    expected_mc = _absolute_from_sign_dms(case["reference"]["angles"]["mc"])
    assert _arcmin_diff(chart.angles["asc"], expected_asc) <= tolerance_arcmin
    assert _arcmin_diff(chart.angles["mc"], expected_mc) <= tolerance_arcmin

    for house_no, expected_text in case["reference"]["houses"].items():
        expected_abs = _absolute_from_sign_dms(expected_text)
        got_abs = chart.houses.cusps[house_no]
        assert _arcmin_diff(got_abs, expected_abs) <= tolerance_arcmin


def test_radix_reference_ufa_planets_within_arcminute_or_marked_pending() -> None:
    case = _load_case("ufa_1984_10_25_142830_radix")
    source = case["input"]
    tolerance_arcmin = float(case["tolerances"]["planets_ok_arcmin"])
    payload = ChartRequest(
        datetime_utc=_to_utc_z(source["datetime_local"], source["timezone_name"]),
        latitude=source["latitude"],
        longitude=source["longitude"],
        house_system=source["house_system"],
        zodiac_mode=source["zodiac_mode"],
        sidereal_mode=source["sidereal_mode"],
        aspect_orb_profile=source["aspect_orb_profile"],
    )
    chart = EphemerisService(ephe_path="ephe").calculate_chart(payload)

    missing_nonblocking = {"lilith", "selena", "proserpina"}
    missing_actual: set[str] = set()
    for object_name, expected_text in case["reference"]["objects"].items():
        if object_name not in chart.objects:
            missing_actual.add(object_name)
            continue
        expected_abs = _absolute_from_sign_dms(expected_text)
        got_abs = chart.objects[object_name].absolute_degree_0_360
        assert _arcmin_diff(got_abs, expected_abs) <= tolerance_arcmin

    assert missing_actual.issubset(missing_nonblocking)
