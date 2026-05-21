from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.models.event_models import DatePrecision, EventCard, EventType, LifeArea, Reversibility
from app.models.response_models import ChartResponse
from app.services.rectification_formula.formula_card_loader import (
    FormulaCardLoader,
    FormulaCardValidationError,
)
from app.services.rectification_formula.formula_test_mode_service import FormulaTestModeService


def test_all_requested_formula_cards_load_successfully() -> None:
    loader = FormulaCardLoader()
    cards = {card.card_id: card for card in loader.list_cards()}

    assert {
        "RECT_CHILD_BIRTH_001",
        "RECT_DEATH_CLOSE_PERSON_001",
        "RECT_MARRIAGE_UNION_001",
        "RECT_RELATIONSHIP_START_001",
        "RECT_DIVORCE_BREAKUP_001",
    }.issubset(cards.keys())


def test_invalid_card_fails_with_clear_validation_error(tmp_path: Path) -> None:
    broken_dir = tmp_path / "cards"
    broken_dir.mkdir()
    broken_path = broken_dir / "broken.json"
    broken_path.write_text(json.dumps({"card_id": "BROKEN"}), encoding="utf-8")

    loader = FormulaCardLoader(cards_root=broken_dir)

    with pytest.raises(FormulaCardValidationError) as exc:
        loader.list_cards()

    assert "missing required fields" in str(exc.value)
    assert "event_type" in str(exc.value)


def test_child_birth_card_contains_house_5_and_house_4_core() -> None:
    loader = FormulaCardLoader()
    card = loader.load_card("RECT_CHILD_BIRTH_001")

    assert "house_5" in card.core_logic
    assert "house_4" in card.core_logic


def test_death_close_person_card_contains_expected_core_and_planets() -> None:
    loader = FormulaCardLoader()
    card = loader.load_card("RECT_DEATH_CLOSE_PERSON_001")

    assert "house_of_deceased_person" in card.core_logic
    assert "house_8" in card.core_logic
    assert "house_12" in card.core_logic
    assert {"saturn", "pluto"}.issubset(set(card.planets))


@pytest.mark.parametrize(
    ("card_id", "event_type"),
    [
        ("RECT_MARRIAGE_UNION_001", "marriage_union"),
        ("RECT_RELATIONSHIP_START_001", "relationship_start"),
        ("RECT_DIVORCE_BREAKUP_001", "divorce_breakup"),
    ],
)
def test_relationship_cards_load_with_subformulas(card_id: str, event_type: str) -> None:
    loader = FormulaCardLoader()
    card = loader.load_card(card_id)

    assert card.event_type == event_type
    assert card.subformulas


def test_formula_test_mode_returns_structured_json_for_mocked_context() -> None:
    service = FormulaTestModeService()

    result = service.evaluate(
        event_type="child_birth",
        context={
            "indicators": ["house_5", "house_4", "moon", "ruler_5", "angle_link"],
            "weak_indicators": ["single_transit_only"],
            "exclusion_indicators": [],
            "pro_result": {
                "method_results": {
                    "directions": [{"event_id": "e1"}],
                    "solars": [{"event_id": "e1"}],
                    "transits": [{"event_id": "e1"}],
                }
            },
        },
    )

    assert result["card_id"] == "RECT_CHILD_BIRTH_001"
    assert result["event_type"] == "child_birth"
    assert result["status"] == "test"
    assert isinstance(result["matched_indicators"], list)
    assert isinstance(result["missing_indicators"], list)
    assert isinstance(result["weak_indicators"], list)
    assert isinstance(result["exclusion_risks"], list)
    assert result["methods_used"] == ["directions", "solars", "transits"]
    assert isinstance(result["score"], (int, float))
    assert result["confidence"] in {"low", "medium", "high"}
    assert result["explanation_for_expert"]


def _sample_formula_chart() -> ChartResponse:
    return ChartResponse.model_validate(
        {
            "input": {
                "datetime_utc": "2000-01-01T12:00:00Z",
                "latitude": 53.9,
                "longitude": 27.55,
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
            },
            "normalized": {"julian_day_ut": 2451545.0},
            "objects": {
                "sun": {"name": "sun", "longitude_deg": 62.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 1.0, "retrograde": False, "sign_index": 2, "sign_name_en": "Gemini", "sign_degree": 2.0, "sign_degree_dms": "2°00'00\"", "absolute_degree_0_360": 62.0, "house": 5},
                "moon": {"name": "moon", "longitude_deg": 92.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 12.0, "retrograde": False, "sign_index": 3, "sign_name_en": "Cancer", "sign_degree": 2.0, "sign_degree_dms": "2°00'00\"", "absolute_degree_0_360": 92.0, "house": 4},
                "jupiter": {"name": "jupiter", "longitude_deg": 148.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 0.08, "retrograde": False, "sign_index": 4, "sign_name_en": "Leo", "sign_degree": 28.0, "sign_degree_dms": "28°00'00\"", "absolute_degree_0_360": 148.0, "house": 5},
                "venus": {"name": "venus", "longitude_deg": 208.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 1.2, "retrograde": False, "sign_index": 6, "sign_name_en": "Libra", "sign_degree": 28.0, "sign_degree_dms": "28°00'00\"", "absolute_degree_0_360": 208.0, "house": 7},
                "saturn": {"name": "saturn", "longitude_deg": 178.0, "latitude_deg": 0, "distance_au": 1, "speed_longitude_deg_per_day": 0.05, "retrograde": False, "sign_index": 5, "sign_name_en": "Virgo", "sign_degree": 28.0, "sign_degree_dms": "28°00'00\"", "absolute_degree_0_360": 178.0, "house": 6}
            },
            "aspects": [],
            "houses": {
                "system": "P",
                "cusps": {str(i): float((i - 1) * 30) for i in range(1, 13)},
                "cusp_details": {
                    "1": {"absolute_degree_0_360": 0.0, "sign_index": 0, "sign_name_en": "Aries", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "2": {"absolute_degree_0_360": 30.0, "sign_index": 1, "sign_name_en": "Taurus", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "3": {"absolute_degree_0_360": 60.0, "sign_index": 2, "sign_name_en": "Gemini", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "4": {"absolute_degree_0_360": 90.0, "sign_index": 3, "sign_name_en": "Cancer", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "5": {"absolute_degree_0_360": 120.0, "sign_index": 4, "sign_name_en": "Leo", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "6": {"absolute_degree_0_360": 150.0, "sign_index": 5, "sign_name_en": "Virgo", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "7": {"absolute_degree_0_360": 180.0, "sign_index": 6, "sign_name_en": "Libra", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "8": {"absolute_degree_0_360": 210.0, "sign_index": 7, "sign_name_en": "Scorpio", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "9": {"absolute_degree_0_360": 240.0, "sign_index": 8, "sign_name_en": "Sagittarius", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "10": {"absolute_degree_0_360": 270.0, "sign_index": 9, "sign_name_en": "Capricorn", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "11": {"absolute_degree_0_360": 300.0, "sign_index": 10, "sign_name_en": "Aquarius", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""},
                    "12": {"absolute_degree_0_360": 330.0, "sign_index": 11, "sign_name_en": "Pisces", "sign_degree": 0.0, "sign_degree_dms": "0°00'00\""}
                }
            },
            "angles": {"asc": 0.0, "mc": 270.0},
            "meta": {
                "ephemeris_source": "swisseph",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
                "object_constants": {"sun": 0},
                "aspect_orb_profile": "avestan",
                "node_definitions": {}
            },
        }
    )


def _sample_child_birth_event() -> EventCard:
    return EventCard(
        event_id="evt_001",
        event_type=EventType.child_birth,
        title="Рождение ребенка",
        date_text="2028-01-01",
        date_precision=DatePrecision.exact,
        start_date="2028-01-01",
        end_date="2028-01-01",
        impact_level=5,
        reversibility=Reversibility.irreversible,
        life_area=LifeArea.family,
        sequence_number=1,
        notes="",
    )


def test_one_event_can_return_multiple_direction_aspects() -> None:
    service = FormulaTestModeService()

    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
            "pro_result": {"method_results": {"directions": [{"event_id": "evt_001"}], "solars": [{"event_id": "evt_001"}], "transits": [{"event_id": "evt_001"}]}},
        },
    )

    assert len(result["matched_formula_aspects"]) >= 3


def test_directed_cusp_to_natal_planet_and_cusp_aspect_is_detected() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    assert any(item["directed_point"].startswith("cusp_5") and item["natal_target"] == "jupiter" for item in result["matched_formula_aspects"])
    assert any(item["natal_target"] == "cusp_4" for item in result["matched_formula_aspects"])


def test_ruler_based_formula_link_is_detected() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    assert any("ruler_5" in item["formula_rule_matched"] or item["directed_point"].startswith("ruler_5") for item in result["matched_formula_aspects"])


def test_element_of_house_formula_link_is_detected() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    assert any(item["directed_point"].startswith("house_element_5:") for item in result["matched_formula_aspects"])


def test_solar_and_transit_do_not_affect_formula_test_mode_score() -> None:
    service = FormulaTestModeService()
    base_context = {
        "chart_response": _sample_formula_chart().model_dump(mode="json"),
        "candidate_birth_date": date(2000, 1, 1),
        "event": _sample_child_birth_event().model_dump(mode="json"),
        "pro_result": {"method_results": {"directions": [{"event_id": "evt_001"}]}},
    }
    result_base = service.evaluate(event_type="child_birth", context=base_context)
    result_with_debug_methods = service.evaluate(
        event_type="child_birth",
        context={
            **base_context,
            "pro_result": {
                "method_results": {
                    "directions": [{"event_id": "evt_001"}],
                    "solars": [{"event_id": "evt_001"}],
                    "transits": [{"event_id": "evt_001"}],
                }
            },
        },
    )

    assert result_base["score"] == result_with_debug_methods["score"]
