from __future__ import annotations

from datetime import date

from app.models.event_models import DatePrecision, EventCard, EventType, LifeArea, Reversibility
from app.models.rectification_pro_models import CandidateTime, ProAscWindow, RectificationProRunRequest
from app.models.response_models import ChartResponse
from app.services.rectification_pro.candidate_generator import CandidateGenerator
from app.services.rectification_pro.confidence_service import ConfidenceService
from app.services.rectification_pro.directions_service import DirectionsService
from app.services.rectification_pro.scoring_service import ScoringService
from app.services.rectification_pro.solar_service import SolarService
from app.services.rectification_pro.totem_service import TotemService
from app.services.rectification_pro.transit_service import TransitService
from app.services.rectification_pro.timezone_context import resolve_pro_timezone


def _sample_chart() -> ChartResponse:
    return ChartResponse.model_validate(
        {
            "input": {
                "datetime_utc": "1990-05-12T11:35:00Z",
                "latitude": 53.9,
                "longitude": 27.55,
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
            },
            "normalized": {"julian_day_ut": 2448023.983333333},
            "objects": {
                "sun": {"name": "sun", "longitude_deg": 50.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 1.0, "retrograde": False, "sign_index": 1, "sign_name_en": "Taurus", "sign_degree": 20.0, "sign_degree_dms": "20°00'00\"", "absolute_degree_0_360": 50.0, "house": 9},
                "moon": {"name": "moon", "longitude_deg": 120.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 12.0, "retrograde": False, "sign_index": 4, "sign_name_en": "Leo", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\"", "absolute_degree_0_360": 120.0, "house": 1},
                "saturn": {"name": "saturn", "longitude_deg": 210.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 0.1, "retrograde": False, "sign_index": 7, "sign_name_en": "Scorpio", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\"", "absolute_degree_0_360": 210.0, "house": 4},
                "true_node": {"name": "true_node", "longitude_deg": 33.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": -0.1, "retrograde": True, "sign_index": 1, "sign_name_en": "Taurus", "sign_degree": 3.0, "sign_degree_dms": "3°00'00\"", "absolute_degree_0_360": 33.0, "house": 8},
                "mean_node": {"name": "mean_node", "longitude_deg": 32.5, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": -0.1, "retrograde": True, "sign_index": 1, "sign_name_en": "Taurus", "sign_degree": 2.5, "sign_degree_dms": "2°30'00\"", "absolute_degree_0_360": 32.5, "house": 8},
            },
            "aspects": [],
            "houses": {
                "system": "P",
                "cusps": {str(i): float((i - 1) * 30) for i in range(1, 13)},
                "cusp_details": {
                    str(i): {
                        "absolute_degree_0_360": float((i - 1) * 30),
                        "sign_index": i - 1,
                        "sign_name_en": "Aries",
                        "sign_degree": 0.0,
                        "sign_degree_dms": "0°00'00\"",
                    }
                    for i in range(1, 13)
                },
            },
            "angles": {"asc": 120.0, "mc": 210.0},
            "meta": {"ephemeris_source": "swisseph", "zodiac_mode": "tropical", "sidereal_mode": None, "object_constants": {"sun": 0}, "node_definitions": {}},
        }
    )


def _sample_event(event_id: str = "e1") -> EventCard:
    return EventCard(
        event_id=event_id,
        event_type=EventType.children_birth,
        title="Event",
        date_text="2018-09-12",
        date_precision=DatePrecision.exact,
        start_date="2018-09-12",
        end_date="2018-09-12",
        impact_level=5,
        reversibility=Reversibility.irreversible,
        life_area=LifeArea.relationships,
        notes="",
        user_skipped=False,
    )


def test_candidate_generator_respects_bounds_and_step() -> None:
    generator = CandidateGenerator()
    result = generator.generate(
        birth_date_local=date(1990, 5, 12),
        timezone_name="Europe/Moscow",
        asc_windows=[
            ProAscWindow(
                start_local="1990-05-12T14:00:00",
                end_local="1990-05-12T14:20:00",
                sign_name_en="Libra",
                sign_name_ru="Весы",
            )
        ],
        step_minutes=5,
        max_candidates=100,
    )
    assert len(result.candidate_times) == 5
    assert result.candidate_times[0].datetime_local == "1990-05-12T14:00:00"
    assert result.candidate_times[-1].datetime_local == "1990-05-12T14:20:00"


def test_directions_returns_matches_and_age_arc() -> None:
    service = DirectionsService()
    matches = service.evaluate_candidate(
        candidate_chart=_sample_chart(),
        candidate_birth_date=date(1990, 5, 12),
        events=[_sample_event()],
        directions_orbs={"default": 1.0, "luminaries": 1.5, "cusps": 1.0},
    )
    assert matches
    assert matches[0].method == "directions"
    assert isinstance(matches[0].matches, list)


def test_solar_returns_score_without_crash() -> None:
    service = SolarService()
    result = service.evaluate_candidate(candidate_chart=_sample_chart(), events=[_sample_event()])
    assert result
    assert result[0].method == "solar"
    assert result[0].event_score >= 0


def test_transits_exact_vs_non_exact() -> None:
    service = TransitService()
    exact_result = service.evaluate_candidate(candidate_chart=_sample_chart(), events=[_sample_event("exact")])
    assert exact_result[0].method == "transits"
    assert exact_result[0].matches

    non_exact = _sample_event("year")
    non_exact.date_precision = DatePrecision.year
    non_exact.start_date = None
    non_exact.end_date = None
    non_exact.date_text = "2018"
    non_exact_result = service.evaluate_candidate(candidate_chart=_sample_chart(), events=[non_exact])
    assert "non_exact_date_low_weight_transit_check_skipped" in non_exact_result[0].warnings


def test_resolve_pro_timezone_uses_coordinates_when_auto_timezone_name_missing() -> None:
    payload = RectificationProRunRequest(
        birth_date_local=date(1990, 5, 12),
        latitude=55.7558,
        longitude=37.6173,
        timezone_name=None,
        timezone_mode="auto",
        timezone_offset=None,
        asc_windows=[],
        events=[],
    )

    _tzinfo, timezone_used, timezone_offset_used = resolve_pro_timezone(payload)

    assert timezone_used == "Europe/Moscow"
    assert timezone_offset_used is None


def test_totem_returns_degree_index_and_warning() -> None:
    service = TotemService()
    info = service.evaluate_candidate(
        candidate=CandidateTime(
            candidate_id="cand_001",
            datetime_local="1990-05-12T14:00:00",
            datetime_utc="1990-05-12T11:00:00Z",
            asc_sign="Libra",
            asc_degree=4.0,
        )
    )
    assert 1 <= int(info["asc_degree_index"]) <= 360
    assert "totem_database_not_connected" in info["warnings"]


def test_scoring_and_confidence_rules() -> None:
    scoring = ScoringService()
    confidence = ConfidenceService()
    event = _sample_event()
    method_results = {
        "directions": [],
        "solar": [],
        "transits": [],
    }
    candidate_score = scoring.score_candidate(
        candidate_id="cand_001",
        candidate_time_local="1990-05-12T14:35:00",
        source_asc_interval=None,
        clipped_by_birth_date=False,
        method_results=method_results,
        events=[event],
        weights={"directions": 0.45, "solar": 0.2, "transits": 0.2, "lunar": 0.1, "totem": 0.05},
    )
    summary = confidence.summarize(best_candidate=candidate_score, events=[event])
    assert summary.level in {"low", "medium", "high", "expert_high"}
    assert summary.level != "expert_high"


def test_candidate_generator_clips_boundaries_and_preserves_duplicate_intervals() -> None:
    generator = CandidateGenerator()
    result = generator.generate(
        birth_date_local=date(1978, 3, 19),
        timezone_name="Asia/Yekaterinburg",
        asc_windows=[
            ProAscWindow(
                start_local="1978-03-18T22:09:22",
                end_local="1978-03-19T00:41:14",
                sign_name_en="Scorpio",
                sign_name_ru="Скорпион",
            ),
            ProAscWindow(
                start_local="1978-03-19T22:05:00",
                end_local="1978-03-20T00:15:00",
                sign_name_en="Scorpio",
                sign_name_ru="Скорпион",
            ),
        ],
        step_minutes=5,
        max_candidates=1000,
    )
    assert result.candidate_times
    locals_all = [item.datetime_local for item in result.candidate_times]
    assert any(value.startswith("1978-03-19T00:") for value in locals_all)
    assert any(value.startswith("1978-03-19T22:") for value in locals_all)
    assert all("1978-03-19T" in value for value in locals_all)
    assert "candidate_windows_clipped_to_birth_date" in result.warnings


def test_candidate_generator_never_outputs_candidates_outside_selected_birth_day() -> None:
    generator = CandidateGenerator()
    result = generator.generate(
        birth_date_local=date(1990, 5, 12),
        timezone_name="Europe/Moscow",
        asc_windows=[
            ProAscWindow(
                start_local="1990-05-11T23:55:00",
                end_local="1990-05-13T00:05:00",
                sign_name_en="Libra",
                sign_name_ru="Весы",
            )
        ],
        step_minutes=5,
        max_candidates=1000,
    )
    assert result.candidate_times
    assert all("1990-05-12T" in item.datetime_local for item in result.candidate_times)
    assert all(item.datetime_local >= "1990-05-12T00:00:00" for item in result.candidate_times)
    assert all(item.datetime_local < "1990-05-13T00:00:00" for item in result.candidate_times)
