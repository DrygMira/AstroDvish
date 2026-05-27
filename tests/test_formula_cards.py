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

CONFIRMED_CHILD_BIRTH_DISPLAY_FORMULAS = [
    "Directed ruler_4 -> Natal house_element_5",
    "Directed cusp_10 -> Natal cusp_5",
    "Directed cusp_6 -> Natal Sun",
    "Directed cusp_4 -> Natal Moon",
    "Directed Sun -> Natal Jupiter",
    "Directed cusp_5 -> Natal Chiron",
]

OLD_CHILD_BIRTH_RULE_IDS = {
    "ruler_5_to_cusp_4",
    "cusp_5_to_significators",
    "house_element_5_to_cusp_7",
    "moon_to_cusp_5",
}


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


def test_production_child_birth_card_contains_exact_confirmed_six_formulas() -> None:
    loader = FormulaCardLoader()
    card = loader.load_card("RECT_CHILD_BIRTH_001")

    formulas = [
        f"Directed {rule.display_source or ', '.join(rule.source_selectors)} -> Natal {rule.display_target or ', '.join(rule.target_selectors)}"
        for rule in card.direction_rules
    ]
    assert formulas == CONFIRMED_CHILD_BIRTH_DISPLAY_FORMULAS
    assert not OLD_CHILD_BIRTH_RULE_IDS.intersection({rule.id for rule in card.direction_rules})
    assert card.card_hash
    assert card.source_file_path
    assert card.card_version == "child_birth_solar_arc_v2"


def test_production_child_birth_card_marks_confirmed_golden_formulas() -> None:
    loader = FormulaCardLoader()
    card = loader.load_card("RECT_CHILD_BIRTH_001")
    by_id = {rule.id: rule for rule in card.direction_rules}

    assert by_id["ruler_4_to_house_element_5"].priority_tier == "golden"
    assert by_id["sun_to_jupiter"].priority_tier == "golden"
    assert by_id["cusp_6_to_sun"].priority_tier == "golden"
    assert by_id["cusp_10_to_cusp_5"].priority_tier == "supporting"
    assert by_id["cusp_4_to_moon"].priority_tier == "supporting"
    assert by_id["cusp_5_to_chiron"].priority_tier == "supporting"


def test_production_child_birth_card_uses_literal_formula_dsl_and_fixed_aspect_names() -> None:
    loader = FormulaCardLoader()
    card = loader.load_card("RECT_CHILD_BIRTH_001")
    by_id = {rule.id: rule for rule in card.direction_rules}

    assert by_id["ruler_4_to_house_element_5"].formula == "Directed ruler_4 -> Natal house_element_5"
    assert by_id["ruler_4_to_house_element_5"].rule == "Directed primary/modern ruler of 4th to natal element of 5th house"
    assert by_id["ruler_4_to_house_element_5"].source == "ruler_4"
    assert by_id["ruler_4_to_house_element_5"].target == "house_element_5"
    assert by_id["ruler_4_to_house_element_5"].source_layer == "directed"
    assert by_id["ruler_4_to_house_element_5"].target_layer == "natal"
    assert by_id["ruler_4_to_house_element_5"].aspect == "square"
    assert by_id["ruler_4_to_house_element_5"].priority == "golden"
    assert by_id["ruler_4_to_house_element_5"].role == "event_confirmation"
    assert by_id["ruler_4_to_house_element_5"].orb_limit == 1.0
    assert by_id["ruler_4_to_house_element_5"].meaning
    assert by_id["ruler_4_to_house_element_5"].comment

    assert by_id["cusp_4_to_moon"].aspect_types == ["trine"]
    assert by_id["cusp_4_to_moon"].aspect == "trine"


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
    assert result["card_hash"]
    assert result["source_file_path"]
    assert result["card_version"] == "child_birth_solar_arc_v2"
    assert isinstance(result["matched_indicators"], list)
    assert isinstance(result["missing_indicators"], list)
    assert isinstance(result["weak_indicators"], list)
    assert isinstance(result["exclusion_risks"], list)
    assert result["methods_used"] == ["directions", "solars", "transits"]
    assert isinstance(result["score"], (int, float))
    assert result["confidence"] in {"low", "medium", "high"}
    assert result["explanation_for_expert"]
    assert "validation_report" in result


def test_reverse_formulas_are_not_auto_created(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_LITERAL_DIRECTION_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["sun", "moon"],
                "houses": ["house_5"],
                "planets": ["sun", "moon"],
                "significators": ["sun"],
                "aspects": ["child_axis"],
                "method_priority": ["directions"],
                "direction_rules": [
                    {
                        "id": "moon_to_sun_only",
                        "title": "Directed Moon to natal Sun only",
                        "formula": "Directed Moon -> Natal Sun",
                        "rule": "Literal direction only",
                        "source_kind": "directed",
                        "target_kind": "natal",
                        "source_selectors": ["moon"],
                        "target_selectors": ["sun"],
                        "aspect_types": ["trine"],
                        "aspect": "trine",
                        "orb_limit": 1.0,
                        "required": True,
                        "weight": 1.0,
                    }
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 92.0, "sign": "Cancer", "house": 5},
            "moon": {"degree": 332.0, "sign": "Pisces", "house": 4},
        },
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _custom_event(title="Literal direction", event_type=EventType.child_birth).model_dump(mode="json"),
        },
    )

    found = {(item["directed_point"], item["natal_target"]) for item in result["matched_formula_aspects"]}
    assert ("moon", "sun") in found
    assert ("sun", "moon") not in found


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


class _FakeSolarArcEphemerisService:
    def calculate_chart(self, payload):
        chart = _sample_formula_chart()
        progressed_sun = chart.objects["sun"].model_copy(update={"absolute_degree_0_360": 77.5})
        return chart.model_copy(update={"objects": {**chart.objects, "sun": progressed_sun}})


def _evaluate_confirmed_child_birth_result(tmp_path: Path) -> dict:
    class _MatchingSolarArcEphemerisService:
        def calculate_chart(self, payload):
            chart = _sample_formula_chart()
            progressed_sun = chart.objects["sun"].model_copy(update={"absolute_degree_0_360": 236.0})
            return chart.model_copy(update={"objects": {**chart.objects, "sun": progressed_sun}})

    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_BIRTH_SOURCE_TARGET_SOLAR_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5", "house_4"],
                "houses": ["house_5", "house_4"],
                "planets": ["sun", "moon", "jupiter", "chiron"],
                "significators": ["moon"],
                "aspects": ["child_axis"],
                "method_priority": ["directions", "solars", "transits"],
                "direction_rules": [
                    {"id": "sig4_to_house5_element", "title": "Directed significator_4 -> natal house_element_5", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["moon"], "target_selectors": ["house_elements_5"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0, "display_source": "significator_4", "display_target": "house_element_5"},
                    {"id": "cusp10_to_cusp5", "title": "Directed cusp_10 -> natal cusp_5", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_10"], "target_selectors": ["cusp_5"], "aspect_types": ["trine"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp6_to_sun", "title": "Directed cusp_6 -> natal Sun", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_6"], "target_selectors": ["sun"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp4_to_moon", "title": "Directed cusp_4 -> natal Moon", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_4"], "target_selectors": ["moon"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "sun_to_jupiter", "title": "Directed Sun -> natal Jupiter", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["sun"], "target_selectors": ["jupiter"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp5_to_chiron", "title": "Directed cusp_5 -> natal Chiron", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_5"], "target_selectors": ["chiron"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                ],
            }
        ],
    )
    service = FormulaTestModeService(
        loader=loader,
        ephemeris_service=_MatchingSolarArcEphemerisService(),
    )
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 208.0, "sign": "Libra", "house": 8},
            "moon": {"degree": 88.0, "sign": "Gemini", "house": 4},
            "jupiter": {"degree": 296.0, "sign": "Sagittarius", "house": 9},
            "chiron": {"degree": 176.0, "sign": "Leo", "house": 6},
            "venus": {"degree": 116.0, "sign": "Cancer", "house": 5},
            "mars": {"degree": 200.0, "sign": "Libra", "house": 9},
        },
        cusps={"1": 0.0, "2": 30.0, "3": 60.0, "4": 60.0, "5": 148.0, "6": 120.0, "7": 180.0, "8": 210.0, "9": 240.0, "10": 0.0, "11": 300.0, "12": 330.0},
        cusp_signs={"1": "Aries", "2": "Taurus", "3": "Gemini", "4": "Cancer", "5": "Leo", "6": "Virgo", "7": "Libra", "8": "Scorpio", "9": "Sagittarius", "10": "Capricorn", "11": "Aquarius", "12": "Pisces"},
    )
    return service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
            "pro_result": {
                "method_results": {
                    "directions": [{"event_id": "evt_001"}],
                    "solars": [{"event_id": "evt_001"}],
                    "transits": [{"event_id": "evt_001"}],
                }
            },
        },
    )


def _custom_event(*, title: str, event_type: EventType = EventType.custom_major_event) -> EventCard:
    return EventCard(
        event_id=f"evt_{title.lower().replace(' ', '_')}",
        event_type=event_type,
        title=title,
        date_text="2000-01-01",
        date_precision=DatePrecision.exact,
        start_date="2000-01-01",
        end_date="2000-01-01",
        impact_level=5,
        reversibility=Reversibility.irreversible,
        life_area=LifeArea.other,
        notes="",
    )


def _build_chart_with_rules(*, objects: dict, cusps: dict[str, float], cusp_signs: dict[str, str]) -> ChartResponse:
    def _obj(name: str, degree: float, sign_name: str, house: int | None = None) -> dict:
        sign_index = {
            "Aries": 0,
            "Taurus": 1,
            "Gemini": 2,
            "Cancer": 3,
            "Leo": 4,
            "Virgo": 5,
            "Libra": 6,
            "Scorpio": 7,
            "Sagittarius": 8,
            "Capricorn": 9,
            "Aquarius": 10,
            "Pisces": 11,
        }[sign_name]
        sign_degree = degree % 30
        return {
            "name": name,
            "longitude_deg": degree,
            "latitude_deg": 0,
            "distance_au": 1,
            "speed_longitude_deg_per_day": 1.0,
            "retrograde": False,
            "sign_index": sign_index,
            "sign_name_en": sign_name,
            "sign_degree": sign_degree,
            "sign_degree_dms": f"{sign_degree:.0f}°00'00\"",
            "absolute_degree_0_360": degree,
            "house": house,
        }

    chart_objects = {
        name: _obj(name, payload["degree"], payload["sign"], payload.get("house"))
        for name, payload in objects.items()
    }
    cusp_details = {
        house_num: {
            "absolute_degree_0_360": degree,
            "sign_index": {
                "Aries": 0,
                "Taurus": 1,
                "Gemini": 2,
                "Cancer": 3,
                "Leo": 4,
                "Virgo": 5,
                "Libra": 6,
                "Scorpio": 7,
                "Sagittarius": 8,
                "Capricorn": 9,
                "Aquarius": 10,
                "Pisces": 11,
            }[cusp_signs[house_num]],
            "sign_name_en": cusp_signs[house_num],
            "sign_degree": degree % 30,
            "sign_degree_dms": f"{degree % 30:.0f}°00'00\"",
        }
        for house_num, degree in cusps.items()
    }
    return ChartResponse.model_validate(
        {
            "input": {
                "datetime_utc": "2000-01-01T00:00:00Z",
                "latitude": 53.9,
                "longitude": 27.55,
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
            },
            "normalized": {"julian_day_ut": 2451544.5},
            "objects": chart_objects,
            "aspects": [],
            "houses": {
                "system": "P",
                "cusps": cusps,
                "cusp_details": cusp_details,
            },
            "angles": {"asc": float(cusps.get("1", 0.0)), "mc": float(cusps.get("10", 270.0))},
            "meta": {
                "ephemeris_source": "swisseph",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
                "object_constants": {"sun": 0},
                "aspect_orb_profile": "avestan",
                "node_definitions": {},
            },
        }
    )


def _write_formula_cards(tmp_path: Path, cards: list[dict]) -> FormulaCardLoader:
    cards_root = tmp_path / "cards"
    cards_root.mkdir()
    for card in cards:
        (cards_root / f"{card['card_id']}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return FormulaCardLoader(cards_root=cards_root)


def test_one_event_can_return_multiple_direction_aspects(tmp_path: Path) -> None:
    result = _evaluate_confirmed_child_birth_result(tmp_path)

    assert len(result["matched_formula_aspects"]) == 6


def test_directed_cusp_to_natal_planet_and_cusp_aspect_is_detected(tmp_path: Path) -> None:
    result = _evaluate_confirmed_child_birth_result(tmp_path)

    assert any(item["directed_point"] == "cusp_10" and item["natal_target"] == "cusp_5" for item in result["matched_formula_aspects"])
    assert any(item["directed_point"] == "cusp_6" and item["natal_target"] == "sun" for item in result["matched_formula_aspects"])


def test_ruler_based_formula_link_is_detected(tmp_path: Path) -> None:
    result = _evaluate_confirmed_child_birth_result(tmp_path)

    assert any(item["formula_rule_matched"] == "sig4_to_house5_element" for item in result["matched_formula_aspects"])


def test_element_of_house_formula_link_is_detected(tmp_path: Path) -> None:
    result = _evaluate_confirmed_child_birth_result(tmp_path)

    assert any(item["natal_target"] == "house_element_5:venus" for item in result["matched_formula_aspects"])


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


def test_validation_report_contains_expected_by_card() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    report = result["validation_report"]
    assert report["event_type"] == "child_birth"
    assert report["card_id"] == "RECT_CHILD_BIRTH_001"
    assert report["card_hash"]
    assert report["source_file_path"]
    assert report["card_version"] == "child_birth_solar_arc_v2"
    assert "house_5" in report["expected_by_card"]["core_logic"]
    assert "house_4" in report["expected_by_card"]["core_logic"]


def test_validation_report_expected_by_card_uses_confirmed_child_birth_formulas() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    rules = result["validation_report"]["expected_by_card"]["direction_rules"]
    assert [rule["display_formula"] for rule in rules] == CONFIRMED_CHILD_BIRTH_DISPLAY_FORMULAS
    assert not OLD_CHILD_BIRTH_RULE_IDS.intersection({rule["id"] for rule in rules})


def test_validation_report_uses_found_and_missed_engine_data() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    report = result["validation_report"]
    assert report["found_by_engine"] == result["matched_formula_aspects"]
    assert report["missed_by_engine"] == result["missing_formula_links"]


def test_validation_report_rejected_aspects_include_reason() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    report = result["validation_report"]
    assert report["rejected_aspects"]
    assert all(item["reason"] for item in report["rejected_aspects"])


def test_validation_report_has_score_breakdown() -> None:
    service = FormulaTestModeService()
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": _sample_formula_chart().model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
        },
    )

    breakdown = result["validation_report"]["score_breakdown"]
    assert "matched_core_points" in breakdown
    assert "matched_formula_aspect_points" in breakdown
    assert "method_points" in breakdown


def test_child_birth_real_formulas_resolve_directed_source_and_natal_target_explicitly(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_BIRTH_SOURCE_TARGET_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5", "house_4"],
                "houses": ["house_5", "house_4"],
                "planets": ["sun", "moon", "jupiter", "chiron"],
                "significators": ["moon"],
                "aspects": ["child_axis"],
                "method_priority": ["directions", "solars", "transits"],
                "direction_rules": [
                    {"id": "sig4_to_house5_element", "title": "Directed significator_4 -> natal house_element_5", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["moon"], "target_selectors": ["house_elements_5"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0, "display_source": "significator_4", "display_target": "house_element_5"},
                    {"id": "cusp10_to_cusp5", "title": "Directed cusp_10 -> natal cusp_5", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_10"], "target_selectors": ["cusp_5"], "aspect_types": ["trine"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp6_to_sun", "title": "Directed cusp_6 -> natal Sun", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_6"], "target_selectors": ["sun"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp4_to_moon", "title": "Directed cusp_4 -> natal Moon", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_4"], "target_selectors": ["moon"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "sun_to_jupiter", "title": "Directed Sun -> natal Jupiter", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["sun"], "target_selectors": ["jupiter"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp5_to_chiron", "title": "Directed cusp_5 -> natal Chiron", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_5"], "target_selectors": ["chiron"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 180.0, "sign": "Libra", "house": 8},
            "moon": {"degree": 60.0, "sign": "Gemini", "house": 4},
            "jupiter": {"degree": 240.5, "sign": "Sagittarius", "house": 9},
            "chiron": {"degree": 120.0, "sign": "Leo", "house": 6},
            "venus": {"degree": 60.0, "sign": "Gemini", "house": 5},
            "mars": {"degree": 200.0, "sign": "Libra", "house": 9},
        },
        cusps={"1": 0.0, "2": 30.0, "3": 60.0, "4": 60.0, "5": 120.0, "6": 120.0, "7": 180.0, "8": 210.0, "9": 240.0, "10": 0.0, "11": 300.0, "12": 330.0},
        cusp_signs={"1": "Aries", "2": "Taurus", "3": "Gemini", "4": "Cancer", "5": "Leo", "6": "Virgo", "7": "Libra", "8": "Scorpio", "9": "Sagittarius", "10": "Capricorn", "11": "Aquarius", "12": "Pisces"},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _custom_event(title="Child", event_type=EventType.child_birth).model_dump(mode="json"),
        },
    )
    report = result["validation_report"]
    formulas = report["expected_by_card"]["direction_rules"]
    assert all(rule["source_kind"] == "directed" for rule in formulas)
    assert all(rule["target_kind"] == "natal" for rule in formulas)
    assert any(rule["display_formula"] == "Directed significator_4 -> Natal house_element_5" for rule in formulas)
    found = {(item["formula_rule_matched"], item["directed_point"], item["natal_target"]) for item in result["matched_formula_aspects"]}
    assert ("sig4_to_house5_element", "moon", "house_element_5:venus") in found
    assert ("cusp10_to_cusp5", "cusp_10", "cusp_5") in found
    assert ("cusp6_to_sun", "cusp_6", "sun") in found
    assert ("cusp4_to_moon", "cusp_4", "moon") in found
    assert ("sun_to_jupiter", "sun", "jupiter") in found
    assert ("cusp5_to_chiron", "cusp_5", "chiron") in found


def test_house_element_5_returns_only_planets_really_in_house_5(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_HOUSE_ELEMENTS_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5"],
                "houses": ["house_5"],
                "planets": ["venus", "mars"],
                "significators": ["moon"],
                "aspects": ["child_axis"],
                "method_priority": ["directions"],
                "direction_rules": [
                    {"id": "sig4_to_house5_element", "title": "Directed significator_4 -> natal house_element_5", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["moon"], "target_selectors": ["house_elements_5"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0}
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={
            "moon": {"degree": 60.0, "sign": "Gemini", "house": 4},
            "venus": {"degree": 60.0, "sign": "Gemini", "house": 5},
            "mars": {"degree": 60.0, "sign": "Gemini", "house": 8},
            "saturn": {"degree": 60.0, "sign": "Gemini", "house": 9},
        },
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={"chart_response": chart.model_dump(mode="json"), "candidate_birth_date": date(2000, 1, 1), "event": _custom_event(title="Child", event_type=EventType.child_birth).model_dump(mode="json")},
    )
    targets = {item["natal_target"] for item in result["matched_formula_aspects"]}
    assert "house_element_5:venus" in targets
    assert "house_element_5:mars" not in targets
    assert "house_element_5:saturn" not in targets


def test_rejected_huge_deviation_is_not_meaningful_candidate_and_report_has_rule_debug(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_REJECTED_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5"],
                "houses": ["house_5"],
                "planets": ["sun", "jupiter"],
                "significators": ["sun"],
                "aspects": ["child_axis"],
                "method_priority": ["directions"],
                "direction_rules": [
                    {"id": "sun_to_jupiter", "title": "Directed Sun -> natal Jupiter", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["sun"], "target_selectors": ["jupiter"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0}
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 180.0, "sign": "Libra", "house": 5},
            "jupiter": {"degree": 261.0, "sign": "Sagittarius", "house": 9},
        },
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={"chart_response": chart.model_dump(mode="json"), "candidate_birth_date": date(2000, 1, 1), "event": _custom_event(title="Child", event_type=EventType.child_birth).model_dump(mode="json")},
    )
    assert not result["matched_formula_aspects"]
    assert result["rejected_aspects"]
    rejected = result["rejected_aspects"][0]
    assert rejected["formula_rule_matched"] == "sun_to_jupiter"
    assert rejected["rejection_reason"] == "over_orb"
    assert rejected["orb"] >= 20.0
    assert rejected["actual_angle"] == 81.0
    assert rejected["exact_angle"] == 60.0
    report = result["validation_report"]
    assert report["missed_by_engine"]
    assert report["rejected_aspects"][0]["reason"] == "over_orb"
    assert report["rule_debug"]
    debug = report["rule_debug"][0]
    assert debug["resolved_sources"] == ["sun"]
    assert debug["resolved_targets"] == ["jupiter"]
    assert debug["direction_method"] == "symbolic_1deg_per_year"
    assert "direction_arc" in debug
    assert debug["checked_pairs"]
    assert debug["matched_pairs"] == []
    assert debug["rejected_pairs"]
    checked_pair = debug["checked_pairs"][0]
    assert checked_pair["source_coordinate_type"] == "directed"
    assert checked_pair["target_coordinate_type"] == "natal"
    assert "source_natal_coordinate" in checked_pair
    assert "directed_coordinate" in checked_pair
    assert "natal_coordinate" in checked_pair


def test_formula_matcher_never_matches_natal_natal_or_directed_directed_layers(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_LAYER_DISCIPLINE_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5"],
                "houses": ["house_5"],
                "planets": ["sun", "jupiter"],
                "significators": ["sun"],
                "aspects": ["child_axis"],
                "method_priority": ["directions"],
                "direction_rules": [
                    {"id": "sun_to_jupiter", "title": "Directed Sun -> natal Jupiter", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["sun"], "target_selectors": ["jupiter"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0}
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 180.0, "sign": "Libra", "house": 5},
            "jupiter": {"degree": 268.0, "sign": "Sagittarius", "house": 9},
        },
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={"chart_response": chart.model_dump(mode="json"), "candidate_birth_date": date(2000, 1, 1), "event": _sample_child_birth_event().model_dump(mode="json")},
    )

    assert result["matched_formula_aspects"]
    match = result["matched_formula_aspects"][0]
    assert match["actual_angle"] == pytest.approx(60.0, abs=0.2)


def test_formula_test_mode_uses_symbolic_age_arc_by_default_even_when_ephemeris_available(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_SOLAR_ARC_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5"],
                "houses": ["house_5"],
                "planets": ["sun", "jupiter"],
                "significators": ["sun"],
                "aspects": ["child_axis"],
                "method_priority": ["directions"],
                "direction_rules": [
                    {"id": "sun_to_jupiter", "title": "Directed Sun -> natal Jupiter", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["sun"], "target_selectors": ["jupiter"], "aspect_types": ["trine"], "orb_limit": 1.0, "required": True, "weight": 1.0}
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader, ephemeris_service=_FakeSolarArcEphemerisService())
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 62.0, "sign": "Gemini", "house": 5},
            "jupiter": {"degree": 210.0, "sign": "Scorpio", "house": 9},
        },
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={"chart_response": chart.model_dump(mode="json"), "candidate_birth_date": date(2000, 1, 1), "event": _sample_child_birth_event().model_dump(mode="json")},
    )

    assert result["debug"]["direction_method"] == "symbolic_1deg_per_year"
    match = result["matched_formula_aspects"][0]
    expected_arc = (date(2028, 1, 1) - date(2000, 1, 1)).days / 365.2425
    assert match["direction_method"] == "symbolic_1deg_per_year"
    assert match["direction_arc"] == pytest.approx(expected_arc, abs=1e-6)
    assert match["directed_source_longitude"] == pytest.approx((62.0 + expected_arc) % 360.0, abs=1e-4)
    assert match["natal_target_longitude"] == pytest.approx(210.0, abs=1e-6)
    assert match["match_status"] == "matched"


def test_formula_test_mode_defaults_to_symbolic_age_arc_when_ephemeris_available() -> None:
    service = FormulaTestModeService(ephemeris_service=_FakeSolarArcEphemerisService())
    assert service.default_direction_method == "symbolic_1deg_per_year"


def test_child_birth_six_formulas_are_found_under_solar_arc(tmp_path: Path) -> None:
    class _MatchingSolarArcEphemerisService:
        def calculate_chart(self, payload):
            chart = _sample_formula_chart()
            progressed_sun = chart.objects["sun"].model_copy(update={"absolute_degree_0_360": 236.0})
            return chart.model_copy(update={"objects": {**chart.objects, "sun": progressed_sun}})

    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_BIRTH_SOURCE_TARGET_SOLAR_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5", "house_4"],
                "houses": ["house_5", "house_4"],
                "planets": ["sun", "moon", "jupiter", "chiron"],
                "significators": ["moon"],
                "aspects": ["child_axis"],
                "method_priority": ["directions", "solars", "transits"],
                "direction_rules": [
                    {"id": "sig4_to_house5_element", "title": "Directed significator_4 -> natal house_element_5", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["moon"], "target_selectors": ["house_elements_5"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0, "display_source": "significator_4", "display_target": "house_element_5"},
                    {"id": "cusp10_to_cusp5", "title": "Directed cusp_10 -> natal cusp_5", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_10"], "target_selectors": ["cusp_5"], "aspect_types": ["trine"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp6_to_sun", "title": "Directed cusp_6 -> natal Sun", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_6"], "target_selectors": ["sun"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp4_to_moon", "title": "Directed cusp_4 -> natal Moon", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_4"], "target_selectors": ["moon"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "sun_to_jupiter", "title": "Directed Sun -> natal Jupiter", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["sun"], "target_selectors": ["jupiter"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp5_to_chiron", "title": "Directed cusp_5 -> natal Chiron", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_5"], "target_selectors": ["chiron"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader, ephemeris_service=_MatchingSolarArcEphemerisService())
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 208.0, "sign": "Libra", "house": 8},
            "moon": {"degree": 88.0, "sign": "Gemini", "house": 4},
            "jupiter": {"degree": 296.0, "sign": "Sagittarius", "house": 9},
            "chiron": {"degree": 176.0, "sign": "Leo", "house": 6},
            "venus": {"degree": 116.0, "sign": "Cancer", "house": 5},
            "mars": {"degree": 200.0, "sign": "Libra", "house": 9},
        },
        cusps={"1": 0.0, "2": 30.0, "3": 60.0, "4": 60.0, "5": 148.0, "6": 120.0, "7": 180.0, "8": 210.0, "9": 240.0, "10": 0.0, "11": 300.0, "12": 330.0},
        cusp_signs={"1": "Aries", "2": "Taurus", "3": "Gemini", "4": "Cancer", "5": "Leo", "6": "Virgo", "7": "Libra", "8": "Scorpio", "9": "Sagittarius", "10": "Capricorn", "11": "Aquarius", "12": "Pisces"},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _sample_child_birth_event().model_dump(mode="json"),
            "direction_method": "solar_arc",
        },
    )

    assert result["debug"]["direction_method"] == "solar_arc"
    assert all(item["direction_method"] == "solar_arc" for item in result["matched_formula_aspects"])
    found = {(item["formula_rule_matched"], item["directed_point"], item["natal_target"]) for item in result["matched_formula_aspects"]}
    assert ("sig4_to_house5_element", "moon", "house_element_5:venus") in found
    assert ("cusp10_to_cusp5", "cusp_10", "cusp_5") in found
    assert ("cusp6_to_sun", "cusp_6", "sun") in found
    assert ("cusp4_to_moon", "cusp_4", "moon") in found
    assert ("sun_to_jupiter", "sun", "jupiter") in found
    assert ("cusp5_to_chiron", "cusp_5", "chiron") in found


def test_optional_chiron_and_proserpina_points_do_not_crash_if_missing(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_OPTIONAL_POINTS_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5"],
                "houses": ["house_5"],
                "planets": ["chiron", "proserpina"],
                "significators": ["sun"],
                "aspects": ["child_axis"],
                "method_priority": ["directions"],
                "direction_rules": [
                    {"id": "cusp5_to_optional_school_points", "title": "Directed cusp_5 -> natal Chiron/Proserpina", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["cusp_5"], "target_selectors": ["chiron", "proserpina"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0}
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={"sun": {"degree": 62.0, "sign": "Gemini", "house": 5}},
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={"chart_response": chart.model_dump(mode="json"), "candidate_birth_date": date(2000, 1, 1), "event": _sample_child_birth_event().model_dump(mode="json")},
    )

    assert result["matched_formula_aspects"] == []
    assert any(item["reason"] == "unresolved_target" for item in result["missing_formula_links"])


def test_quincunx_is_debug_only_and_does_not_affect_mvp_score(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_CHILD_QUINCUNX_DEBUG_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5"],
                "houses": ["house_5"],
                "planets": ["sun", "moon"],
                "significators": ["sun"],
                "aspects": ["child_axis"],
                "method_priority": ["directions"],
                "direction_rules": [
                    {"id": "sun_to_moon_quincunx", "title": "Directed Sun -> natal Moon", "source_kind": "directed", "target_kind": "natal", "source_selectors": ["sun"], "target_selectors": ["moon"], "aspect_types": ["quincunx"], "orb_limit": 1.0, "required": False, "weight": 1.0}
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={
            "sun": {"degree": 180.0, "sign": "Libra", "house": 5},
            "moon": {"degree": 358.0, "sign": "Pisces", "house": 4},
        },
        cusps={str(i): float((i - 1) * 30) for i in range(1, 13)},
        cusp_signs={str(i): name for i, name in enumerate(["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"], start=1)},
    )
    result = service.evaluate(
        event_type="child_birth",
        context={"chart_response": chart.model_dump(mode="json"), "candidate_birth_date": date(2000, 1, 1), "event": _sample_child_birth_event().model_dump(mode="json")},
    )

    assert result["matched_formula_aspects"]
    assert result["matched_formula_aspects"][0]["aspect_type"] == "quincunx"
    assert result["validation_report"]["method_scope"]["debug_optional_aspects"] == ["quincunx"]
    assert result["validation_report"]["score_breakdown"]["matched_formula_aspect_points"] == 0.0


def test_ekaterina_marriage_cases_are_found_and_over_orb_goes_to_rejected(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_MARRIAGE_UNION_EK_001",
                "event_type": "marriage_union",
                "status": "test",
                "core_logic": ["house_7", "house_4", "venus"],
                "houses": ["house_7", "house_4"],
                "planets": ["venus", "jupiter", "moon", "chiron", "pluto", "neptune", "sun"],
                "significators": ["venus", "jupiter", "moon"],
                "aspects": ["union_axis"],
                "method_priority": ["directions", "solars", "transits"],
                "direction_rules": [
                    {"id": "cusp_4_to_ruler_7", "title": "c4->r7", "source_selectors": ["cusp_4"], "target_selectors": ["ruler_7", "significators"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "ruler_1_to_cusp_7", "title": "r1->c7", "source_selectors": ["ruler_1"], "target_selectors": ["cusp_7"], "aspect_types": ["opposition"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "cusp_7_to_house_elements_4", "title": "c7->house4", "source_selectors": ["cusp_7"], "target_selectors": ["house_elements_4"], "aspect_types": ["square"], "orb_limit": 1.0, "required": False, "weight": 1.0},
                    {"id": "chiron_to_cusp_3", "title": "chiron->c3", "source_selectors": ["chiron"], "target_selectors": ["cusp_3"], "aspect_types": ["trine"], "orb_limit": 1.0, "required": False, "weight": 1.0},
                    {"id": "jupiter_to_cusp_7", "title": "jupiter->c7", "source_selectors": ["jupiter"], "target_selectors": ["cusp_7"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": False, "weight": 1.0},
                    {"id": "moon_to_jupiter", "title": "moon->jupiter", "source_selectors": ["moon"], "target_selectors": ["jupiter"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": False, "weight": 1.0},
                    {"id": "cusp_1_to_ruler_4", "title": "c1->r4", "source_selectors": ["cusp_1"], "target_selectors": ["ruler_4"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": False, "weight": 1.0},
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={
            "venus": {"degree": 30.0, "sign": "Taurus", "house": 7},
            "pluto": {"degree": 0.0, "sign": "Scorpio", "house": 1},
            "sun": {"degree": 272.0, "sign": "Capricorn", "house": 4},
            "chiron": {"degree": 180.0, "sign": "Libra", "house": 6},
            "jupiter": {"degree": 120.0, "sign": "Leo", "house": 5},
            "moon": {"degree": 60.0, "sign": "Gemini", "house": 2},
            "neptune": {"degree": 330.0, "sign": "Pisces", "house": 4},
        },
        cusps={"1": 330.0, "2": 30.0, "3": 60.0, "4": 30.0, "5": 120.0, "6": 150.0, "7": 180.0, "8": 210.0, "9": 240.0, "10": 270.0, "11": 300.0, "12": 330.0},
        cusp_signs={"1": "Scorpio", "2": "Taurus", "3": "Gemini", "4": "Pisces", "5": "Leo", "6": "Virgo", "7": "Taurus", "8": "Scorpio", "9": "Sagittarius", "10": "Capricorn", "11": "Aquarius", "12": "Pisces"},
    )
    result = service.evaluate(
        event_type="marriage_union",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _custom_event(title="Marriage", event_type=EventType.marriage_relationship).model_dump(mode="json"),
            "pro_result": {"method_results": {"directions": [{"event_id": "evt_marriage"}], "solars": [{"event_id": "evt_marriage"}], "transits": [{"event_id": "evt_marriage"}]}},
        },
    )

    found = {(item["formula_rule_matched"], item["directed_point"], item["natal_target"], item["aspect_type"]) for item in result["matched_formula_aspects"]}
    rejected = {(item["formula_rule_matched"], item["directed_point"], item["natal_target"], item["aspect_type"], item["rejection_reason"]) for item in result["rejected_aspects"]}

    assert ("cusp_4_to_ruler_7", "cusp_4", "ruler_7:venus", "conjunction") in found
    assert ("ruler_1_to_cusp_7", "ruler_1:pluto", "cusp_7", "opposition") in found
    assert ("chiron_to_cusp_3", "chiron", "cusp_3", "trine") in found
    assert ("jupiter_to_cusp_7", "jupiter", "cusp_7", "sextile") in found
    assert ("moon_to_jupiter", "moon", "jupiter", "sextile") in found
    assert ("cusp_1_to_ruler_4", "cusp_1", "ruler_4:neptune", "conjunction") in found
    assert ("cusp_7_to_house_elements_4", "cusp_7", "house_element_4:sun", "square", "over_orb") in rejected
    assert result["score"] == service.evaluate(
        event_type="marriage_union",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _custom_event(title="Marriage", event_type=EventType.marriage_relationship).model_dump(mode="json"),
            "pro_result": {"method_results": {"directions": [{"event_id": "evt_marriage"}]}},
        },
    )["score"]


def test_ekaterina_death_and_child_cases_are_found(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_DEATH_CLOSE_PERSON_EK_001",
                "event_type": "death_close_person",
                "status": "test",
                "core_logic": ["house_12", "neptune"],
                "houses": ["house_12"],
                "planets": ["neptune"],
                "significators": ["neptune"],
                "aspects": ["loss_axis"],
                "method_priority": ["directions", "transits", "solars"],
                "direction_rules": [
                    {"id": "cusp_12_to_ruler_4", "title": "c12->r4", "source_selectors": ["cusp_12"], "target_selectors": ["ruler_4"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0}
                ],
            },
            {
                "card_id": "RECT_CHILD_BIRTH_EK_001",
                "event_type": "child_birth",
                "status": "test",
                "core_logic": ["house_5", "sun", "jupiter"],
                "houses": ["house_5", "house_4", "house_10"],
                "planets": ["sun", "jupiter"],
                "significators": ["sun"],
                "aspects": ["child_axis"],
                "method_priority": ["directions", "solars", "transits"],
                "direction_rules": [
                    {"id": "significator_5_to_jupiter", "title": "sig5->jupiter", "source_selectors": ["significators"], "target_selectors": ["jupiter"], "aspect_types": ["sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "axis_10_4_to_cusp_5", "title": "axis->c5", "source_selectors": ["cusp_10", "cusp_4"], "target_selectors": ["cusp_5"], "aspect_types": ["trine", "sextile"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                ],
            },
        ],
    )
    service = FormulaTestModeService(loader=loader)

    death_chart = _build_chart_with_rules(
        objects={"neptune": {"degree": 330.0, "sign": "Pisces", "house": 4}},
        cusps={"1": 0.0, "2": 30.0, "3": 60.0, "4": 90.0, "5": 120.0, "6": 150.0, "7": 180.0, "8": 210.0, "9": 240.0, "10": 270.0, "11": 300.0, "12": 330.0},
        cusp_signs={"1": "Aries", "2": "Taurus", "3": "Gemini", "4": "Pisces", "5": "Leo", "6": "Virgo", "7": "Libra", "8": "Scorpio", "9": "Sagittarius", "10": "Capricorn", "11": "Aquarius", "12": "Pisces"},
    )
    death_result = service.evaluate(
        event_type="death_close_person",
        context={
            "chart_response": death_chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _custom_event(title="Death", event_type=EventType.death_of_close_person).model_dump(mode="json"),
        },
    )
    assert any(item["formula_rule_matched"] == "cusp_12_to_ruler_4" and item["natal_target"] == "ruler_4:neptune" for item in death_result["matched_formula_aspects"])

    child_chart = _build_chart_with_rules(
        objects={"sun": {"degree": 60.0, "sign": "Gemini", "house": 5}, "jupiter": {"degree": 120.0, "sign": "Leo", "house": 9}},
        cusps={"1": 0.0, "2": 30.0, "3": 60.0, "4": 60.0, "5": 120.0, "6": 150.0, "7": 180.0, "8": 210.0, "9": 240.0, "10": 0.0, "11": 300.0, "12": 330.0},
        cusp_signs={"1": "Aries", "2": "Taurus", "3": "Gemini", "4": "Cancer", "5": "Leo", "6": "Virgo", "7": "Libra", "8": "Scorpio", "9": "Sagittarius", "10": "Capricorn", "11": "Aquarius", "12": "Pisces"},
    )
    child_result = service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": child_chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _custom_event(title="Child", event_type=EventType.child_birth).model_dump(mode="json"),
        },
    )
    found = {(item["formula_rule_matched"], item["directed_point"], item["natal_target"], item["aspect_type"]) for item in child_result["matched_formula_aspects"]}
    assert ("significator_5_to_jupiter", "sun", "jupiter", "sextile") in found
    assert ("axis_10_4_to_cusp_5", "cusp_10", "cusp_5", "trine") in found
    assert ("axis_10_4_to_cusp_5", "cusp_4", "cusp_5", "sextile") in found


def test_ekaterina_divorce_proserpina_case_is_missed_when_ruler_catalog_cannot_resolve_it(tmp_path: Path) -> None:
    loader = _write_formula_cards(
        tmp_path,
        [
            {
                "card_id": "RECT_DIVORCE_BREAKUP_EK_001",
                "event_type": "divorce_breakup",
                "status": "test",
                "core_logic": ["house_7", "house_8"],
                "houses": ["house_7", "house_8", "house_10"],
                "planets": ["venus", "proserpina"],
                "significators": ["venus", "proserpina"],
                "aspects": ["separation_axis"],
                "method_priority": ["directions", "transits", "solars"],
                "direction_rules": [
                    {"id": "cusp_7_to_cusp_8", "title": "c7->c8", "source_selectors": ["cusp_7"], "target_selectors": ["cusp_8"], "aspect_types": ["conjunction"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                    {"id": "ruler_10_to_ruler_7", "title": "r10->r7", "source_selectors": ["ruler_10"], "target_selectors": ["ruler_7"], "aspect_types": ["trine"], "orb_limit": 1.0, "required": True, "weight": 1.0},
                ],
            }
        ],
    )
    service = FormulaTestModeService(loader=loader)
    chart = _build_chart_with_rules(
        objects={"venus": {"degree": 30.0, "sign": "Taurus", "house": 7}, "proserpina": {"degree": 150.0, "sign": "Virgo", "house": 10}},
        cusps={"1": 0.0, "2": 30.0, "3": 60.0, "4": 90.0, "5": 120.0, "6": 150.0, "7": 180.0, "8": 180.0, "9": 240.0, "10": 300.0, "11": 330.0, "12": 350.0},
        cusp_signs={"1": "Aries", "2": "Taurus", "3": "Gemini", "4": "Cancer", "5": "Leo", "6": "Virgo", "7": "Taurus", "8": "Scorpio", "9": "Sagittarius", "10": "Virgo", "11": "Aquarius", "12": "Pisces"},
    )
    result = service.evaluate(
        event_type="divorce_breakup",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(2000, 1, 1),
            "event": _custom_event(title="Divorce", event_type=EventType.divorce_separation).model_dump(mode="json"),
        },
    )

    found = {(item["formula_rule_matched"], item["directed_point"], item["natal_target"], item["aspect_type"]) for item in result["matched_formula_aspects"]}
    assert ("cusp_7_to_cusp_8", "cusp_7", "cusp_8", "conjunction") in found
    assert any(item["rule_id"] == "ruler_10_to_ruler_7" for item in result["missing_formula_links"])
    assert all(item["formula_rule_matched"] != "ruler_10_to_ruler_7" for item in result["matched_formula_aspects"])
