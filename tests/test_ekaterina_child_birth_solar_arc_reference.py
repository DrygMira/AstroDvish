from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.models.event_models import DatePrecision, EventCard, EventType, LifeArea, Reversibility
from app.models.request_models import ChartRequest
from app.services.ephemeris_service import EphemerisService
from app.services.rectification_formula.formula_card_loader import FormulaCardLoader
from app.services.rectification_formula.formula_test_mode_service import FormulaTestModeService

REFERENCE_BIRTH_UTC = "1978-03-19T17:59:45Z"
REFERENCE_LATITUDE = 40.2341666667
REFERENCE_LONGITUDE = 69.6947222222
REFERENCE_EVENT_DATE = "2005-11-07"

REFERENCE_FORMULAS = [
    {
        "id": "ruler_4_to_house_element_5",
        "display_formula": "Directed ruler_4 -> Natal house_element_5",
        "source_selectors": ["ruler_4"],
        "target_selectors": ["house_elements_5"],
        "aspect_types": ["square"],
        "expected_directed_point": "ruler_4:neptune",
        "expected_natal_target": "house_element_5:mercury",
        "expected_directed_longitude": 285.95,
        "expected_natal_longitude": 16.133333,
        "expected_orb": 0.183333,
    },
    {
        "id": "sun_to_jupiter",
        "display_formula": "Directed Sun -> Natal Jupiter",
        "source_selectors": ["sun"],
        "target_selectors": ["jupiter"],
        "aspect_types": ["sextile"],
        "expected_directed_point": "sun",
        "expected_natal_target": "jupiter",
        "expected_directed_longitude": 26.416667,
        "expected_natal_longitude": 87.3,
        "expected_orb": 0.95,
    },
    {
        "id": "cusp_6_to_sun",
        "display_formula": "Directed cusp_6 -> Natal Sun",
        "source_selectors": ["cusp_6"],
        "target_selectors": ["sun"],
        "aspect_types": ["sextile"],
        "expected_directed_point": "cusp_6",
        "expected_natal_target": "sun",
        "expected_directed_longitude": 59.383333,
        "expected_natal_longitude": 358.783333,
        "expected_orb": 0.6,
    },
]


def _reference_event() -> EventCard:
    return EventCard(
        event_id="ek_child_birth_001",
        event_type=EventType.child_birth,
        title="Child birth",
        date_text=REFERENCE_EVENT_DATE,
        date_precision=DatePrecision.exact,
        start_date=REFERENCE_EVENT_DATE,
        end_date=REFERENCE_EVENT_DATE,
        impact_level=5,
        reversibility=Reversibility.irreversible,
        life_area=LifeArea.family,
        sequence_number=1,
        notes="Ekaterina symbolic age arc reference case",
    )


def _reference_card_loader(tmp_path: Path) -> FormulaCardLoader:
    card = {
        "card_id": "RECT_CHILD_BIRTH_EKATERINA_REFERENCE_001",
        "event_type": "child_birth",
        "status": "test",
        "school": "ekaterina_reference",
        "core_logic": ["house_4", "house_5", "sun", "moon", "jupiter", "neptune"],
        "houses": ["house_4", "house_5", "house_6", "house_10"],
        "planets": ["sun", "moon", "mercury", "jupiter", "neptune", "chiron"],
        "significators": ["sun", "moon"],
        "aspects": ["child_birth_reference"],
        "method_priority": ["directions"],
        "direction_rules": [
            {
                "id": item["id"],
                "title": item["display_formula"],
                "source_kind": "directed",
                "target_kind": "natal",
                "source_selectors": item["source_selectors"],
                "target_selectors": item["target_selectors"],
                "aspect_types": item["aspect_types"],
                "orb_limit": 1.0,
                "required": True,
                "weight": 1.0,
                "display_source": item["display_formula"].split(" -> ")[0].replace("Directed ", ""),
                "display_target": item["display_formula"].split(" -> ")[1].replace("Natal ", ""),
            }
            for item in REFERENCE_FORMULAS
        ],
    }
    path = tmp_path / "RECT_CHILD_BIRTH_EKATERINA_REFERENCE_001.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return FormulaCardLoader(cards_root=tmp_path)


def _reference_result(tmp_path: Path) -> dict:
    ephemeris = EphemerisService(ephe_path="ephe")
    chart = ephemeris.calculate_chart(
        ChartRequest(
            datetime_utc=REFERENCE_BIRTH_UTC,
            latitude=REFERENCE_LATITUDE,
            longitude=REFERENCE_LONGITUDE,
            house_system="P",
            zodiac_mode="tropical",
            sidereal_mode=None,
            aspect_orb_profile="avestan",
        )
    )
    service = FormulaTestModeService(
        loader=_reference_card_loader(tmp_path),
        ephemeris_service=ephemeris,
    )
    return service.evaluate(
        event_type="child_birth",
        context={
            "chart_response": chart.model_dump(mode="json"),
            "candidate_birth_date": date(1978, 3, 19),
            "event": _reference_event().model_dump(mode="json"),
        },
    )


def test_ekaterina_child_birth_symbolic_reference_debug_payload(tmp_path: Path) -> None:
    result = _reference_result(tmp_path)

    assert result["card_id"] == "RECT_CHILD_BIRTH_EKATERINA_REFERENCE_001"
    assert result["debug"]["direction_method"] == "symbolic_1deg_per_year"
    assert result["validation_report"]["rule_debug"][0]["direction_arc"] == pytest.approx(27.639171, abs=1e-4)
    assert result["debug"]["directed_points_debug"]
    assert result["debug"]["natal_targets_debug"]
    assert result["validation_report"]["rule_debug"]
    assert result["validation_report"]["expected_by_card"]["direction_rules"]
    checked_pairs = [
        pair
        for rule in result["validation_report"]["rule_debug"]
        for pair in rule["checked_pairs"]
    ]
    assert checked_pairs
    assert all(pair["source_coordinate_type"] == "directed" for pair in checked_pairs)
    assert all(pair["target_coordinate_type"] == "natal" for pair in checked_pairs)


def test_ekaterina_child_birth_symbolic_reference_expected_aspects(tmp_path: Path) -> None:
    result = _reference_result(tmp_path)
    matched = {item["formula_rule_matched"]: item for item in result["matched_formula_aspects"]}
    rejected_pairs = {
        (item["formula_rule_matched"], item["directed_point"], item["natal_target"])
        for item in result["rejected_aspects"]
    }

    for reference in REFERENCE_FORMULAS:
        match = matched.get(reference["id"])
        assert match is not None, {
            "missing_rule": reference["id"],
            "matched_rules": sorted(matched),
            "rejected_pairs": sorted(rejected_pairs),
            "validation_report": result["validation_report"],
        }
        assert match["directed_point"] == reference["expected_directed_point"]
        assert match["natal_target"] == reference["expected_natal_target"]
        assert match["aspect_type"] == reference["aspect_types"][0]
        assert abs(match["directed_source_longitude"] - reference["expected_directed_longitude"]) <= 0.25
        assert abs(match["natal_target_longitude"] - reference["expected_natal_longitude"]) <= 0.25
        assert abs(match["orb"] - reference["expected_orb"]) <= 0.25
        assert (
            reference["id"],
            reference["expected_directed_point"],
            reference["expected_natal_target"],
        ) not in rejected_pairs
