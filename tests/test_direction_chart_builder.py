from __future__ import annotations

from datetime import date
from datetime import datetime, timedelta, timezone

import pytest

from app.services.rectification_formula.direction_chart_builder import DirectionChartBuilder
from tests.test_formula_cards import _build_chart_with_rules, _sample_child_birth_event


def _sample_direction_chart():
    return _build_chart_with_rules(
        objects={
            "sun": {"degree": 180.0, "sign": "Libra", "house": 5},
            "moon": {"degree": 60.0, "sign": "Gemini", "house": 4},
            "jupiter": {"degree": 240.5, "sign": "Sagittarius", "house": 9},
        },
        cusps={"1": 0.0, "2": 30.0, "3": 60.0, "4": 90.0, "5": 120.0, "6": 150.0, "7": 180.0, "8": 210.0, "9": 240.0, "10": 270.0, "11": 300.0, "12": 330.0},
        cusp_signs={"1": "Aries", "2": "Taurus", "3": "Gemini", "4": "Cancer", "5": "Leo", "6": "Virgo", "7": "Libra", "8": "Scorpio", "9": "Sagittarius", "10": "Capricorn", "11": "Aquarius", "12": "Pisces"},
    )


class _FakeEphemerisService:
    def calculate_chart(self, payload):
        chart = _sample_direction_chart()
        progressed_sun = chart.objects["sun"].model_copy(update={"absolute_degree_0_360": 195.5})
        return chart.model_copy(update={"objects": {**chart.objects, "sun": progressed_sun}})


class _CapturingEphemerisService:
    def __init__(self, progressed_sun_longitude: float) -> None:
        self.progressed_sun_longitude = progressed_sun_longitude
        self.last_payload = None

    def calculate_chart(self, payload):
        self.last_payload = payload
        chart = _sample_direction_chart()
        progressed_sun = chart.objects["sun"].model_copy(update={"absolute_degree_0_360": self.progressed_sun_longitude})
        return chart.model_copy(update={"objects": {**chart.objects, "sun": progressed_sun}})


def test_directed_chart_is_separate_from_natal_chart() -> None:
    builder = DirectionChartBuilder()
    chart = _sample_direction_chart()

    result = builder.build(
        natal_chart=chart,
        candidate_birth_date=date(2000, 1, 1),
        event=_sample_child_birth_event(),
    )

    assert result.natal_points is not result.directed_points
    assert result.natal_points["sun"] == 180.0
    assert result.directed_points["sun"] != result.natal_points["sun"]


def test_all_directed_points_shift_by_same_direction_arc_for_symbolic_method() -> None:
    builder = DirectionChartBuilder()
    chart = _sample_direction_chart()

    result = builder.build(
        natal_chart=chart,
        candidate_birth_date=date(2000, 1, 1),
        event=_sample_child_birth_event(),
        direction_method="symbolic_1deg_per_year",
    )

    expected_arc = pytest.approx(result.direction_arc, abs=1e-6)
    for point_key in ("sun", "moon", "jupiter", "cusp_5", "asc", "mc", "desc", "ic"):
        delta = (result.directed_points[point_key] - result.natal_points[point_key]) % 360.0
        assert delta == expected_arc


def test_solar_arc_uses_progressed_sun_minus_natal_sun() -> None:
    builder = DirectionChartBuilder(ephemeris_service=_FakeEphemerisService())
    chart = _sample_direction_chart()

    result = builder.build(
        natal_chart=chart,
        candidate_birth_date=date(2000, 1, 1),
        event=_sample_child_birth_event(),
        direction_method="solar_arc",
    )

    assert result.direction_method == "solar_arc"
    assert result.direction_arc == pytest.approx(15.5, abs=1e-6)
    assert result.directed_points["sun"] == pytest.approx(195.5, abs=1e-6)


def test_solar_arc_normalizes_through_zero_aries() -> None:
    class _WrapEphemerisService:
        def calculate_chart(self, payload):
            chart = _build_chart_with_rules(
                objects={"sun": {"degree": 350.0, "sign": "Pisces", "house": 5}},
                cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
                cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
            )
            progressed_sun = chart.objects["sun"].model_copy(update={"absolute_degree_0_360": 10.0})
            return chart.model_copy(update={"objects": {**chart.objects, "sun": progressed_sun}})

    chart = _build_chart_with_rules(
        objects={"sun": {"degree": 350.0, "sign": "Pisces", "house": 5}},
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    builder = DirectionChartBuilder(ephemeris_service=_WrapEphemerisService())

    result = builder.build(
        natal_chart=chart,
        candidate_birth_date=date(2000, 1, 1),
        event=_sample_child_birth_event(),
        direction_method="solar_arc",
    )

    assert result.direction_arc == pytest.approx(20.0, abs=1e-6)


def test_natal_targets_do_not_move_in_solar_arc_layer() -> None:
    builder = DirectionChartBuilder(ephemeris_service=_FakeEphemerisService())
    chart = _sample_direction_chart()

    result = builder.build(
        natal_chart=chart,
        candidate_birth_date=date(2000, 1, 1),
        event=_sample_child_birth_event(),
        direction_method="solar_arc",
    )

    assert result.natal_points["jupiter"] == pytest.approx(240.5, abs=1e-6)
    assert result.directed_points["jupiter"] == pytest.approx(256.0, abs=1e-6)


def test_gradarch_is_excluded_from_mvp_direction_points() -> None:
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 180.0, "sign": "Libra", "house": 5},
            "gradarch": {"degree": 12.0, "sign": "Aries", "house": 1},
        },
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    builder = DirectionChartBuilder()

    result = builder.build(
        natal_chart=chart,
        candidate_birth_date=date(2000, 1, 1),
        event=_sample_child_birth_event(),
        direction_method="symbolic_1deg_per_year",
    )

    assert "gradarch" not in result.natal_points
    assert "gradarch" not in result.directed_points


def test_solar_arc_uses_secondary_progression_datetime() -> None:
    ephemeris = _CapturingEphemerisService(progressed_sun_longitude=195.5)
    builder = DirectionChartBuilder(ephemeris_service=ephemeris)
    chart = _sample_direction_chart()

    builder.build(
        natal_chart=chart,
        candidate_birth_date=date(2000, 1, 1),
        event=_sample_child_birth_event(),
        direction_method="solar_arc",
    )

    assert ephemeris.last_payload is not None
    expected_age_years = (date(2028, 1, 1) - date(2000, 1, 1)).days / 365.2425
    expected_datetime = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(days=expected_age_years)
    assert ephemeris.last_payload.datetime_utc == expected_datetime
