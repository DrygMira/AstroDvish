from __future__ import annotations

import json
from pathlib import Path

import pytest

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
