from __future__ import annotations

from pathlib import Path

import pytest

from scripts.cardlib import card_io, parser, verify


SAMPLE_META = {
    "title": "Test card",
    "source_meaning": "test meaning",
    "source_comment": "test comment",
    "core_logic": ["house_4", "moon"],
    "houses": ["house_4"],
    "planets": ["moon", "saturn"],
    "significators": ["moon"],
    "aspects": ["test_axis"],
    "strong_confirmation": ["multiple_methods"],
    "weak_confirmation": ["single_transit_only"],
    "exclusions": ["career_only_signature"],
    "expert_note": "test note",
}


SAMPLE_TEXT = """\
Formula: Directed Moon -> Natal Saturn
Rule: R1
Allowed aspects: square, opposition
Priority: golden

Formula: Directed Sun -> Natal Mars
Rule: R2
Allowed aspects: conjunction
Priority: supporting

Formula: Directed Venus -> Natal Jupiter
Rule: R3
Allowed aspects: trine
Priority: context
"""


def test_split_blocks_splits_on_blank_lines() -> None:
    blocks = parser.split_blocks(SAMPLE_TEXT)
    assert len(blocks) == 3
    assert blocks[0].startswith("Formula: Directed Moon")
    assert blocks[2].startswith("Formula: Directed Venus")


def test_parse_block_extracts_fields() -> None:
    block = "Formula: Directed Moon -> Natal Saturn\nRule: R1\nAllowed aspects: square, opposition\nPriority: golden"
    parsed = parser.parse_block(block)
    assert parsed is not None
    assert parsed["source"] == "Moon"
    assert parsed["target"] == "Saturn"
    assert parsed["rule"] == "R1"
    assert parsed["allowed_aspects"] == ["square", "opposition"]
    assert parsed["priority"] == "golden"


def test_parse_block_returns_none_for_malformed() -> None:
    assert parser.parse_block("not a formula block at all") is None


def test_build_direction_rule_shape() -> None:
    parsed = parser.parse_block(
        "Formula: Directed Moon -> Natal Saturn\nRule: R1\n"
        "Allowed aspects: square, opposition\nPriority: golden"
    )
    rule = parser.build_direction_rule(parsed=parsed, meaning="test meaning", comment="test comment", source_note="file.txt block #1")
    assert rule["id"] == "R1"
    assert rule["source"] == "Moon"
    assert rule["target"] == "Saturn"
    assert rule["priority_tier"] == "golden"
    assert rule["required"] is True
    assert rule["weight"] == 1.4
    assert rule["meaning"] == "test meaning"
    assert rule["comment"] == "test comment"
    assert rule["source_note"] == "file.txt block #1"


def test_parse_formulas_end_to_end_unique_rules() -> None:
    result = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="sample.txt")
    assert result.imported_formula_count == 3
    assert result.tier_counts == {"golden": 1, "supporting": 1, "context": 1, "ambiguity_risk": 0}
    assert result.malformed_blocks == []
    assert result.duplicates_report == []
    assert result.conflicts_for_review == []
    assert [r["id"] for r in result.direction_rules] == ["R1", "R2", "R3"]


DUPLICATE_TEXT = """\
Formula: Directed Moon -> Natal Saturn
Rule: R1
Allowed aspects: square
Priority: supporting

Formula: Directed Moon -> Natal Saturn
Rule: R1
Allowed aspects: square
Priority: golden
"""


def test_parse_formulas_resolves_duplicate_to_higher_tier() -> None:
    result = parser.parse_formulas(DUPLICATE_TEXT, meaning="m", comment="c", source_name="dup.txt")
    assert result.imported_formula_count == 1
    assert result.direction_rules[0]["priority_tier"] == "golden"
    assert len(result.duplicates_report) == 1
    assert result.duplicates_report[0]["resolution"] == "replaced_lower_priority_duplicate"
    assert len(result.conflicts_for_review) == 1


MALFORMED_TEXT = """\
Formula: Directed Moon -> Natal Saturn
Rule: R1
Allowed aspects: square
Priority: golden

this block is not parseable at all
"""


def test_parse_formulas_reports_malformed_blocks() -> None:
    result = parser.parse_formulas(MALFORMED_TEXT, meaning="m", comment="c", source_name="bad.txt")
    assert result.imported_formula_count == 1
    assert len(result.malformed_blocks) == 1


def test_load_meta_reads_json_sidecar(tmp_path: Path) -> None:
    import json

    meta_path = tmp_path / "meta.json"
    meta_path.write_text(json.dumps(SAMPLE_META), encoding="utf-8")
    meta = card_io.load_meta(meta_path)
    assert meta.title == "Test card"
    assert meta.houses == ["house_4"]
    assert meta.expert_note == "test note"


def test_load_meta_rejects_missing_required_field(tmp_path: Path) -> None:
    import json

    incomplete = dict(SAMPLE_META)
    del incomplete["core_logic"]
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(json.dumps(incomplete), encoding="utf-8")
    with pytest.raises(card_io.CardMetaError, match="core_logic"):
        card_io.load_meta(meta_path)


def test_build_card_assembles_full_card_dict() -> None:
    meta = card_io.load_meta_dict(SAMPLE_META)
    parsed = parser.parse_formulas(SAMPLE_TEXT, meaning=meta.source_meaning, comment=meta.source_comment, source_name="sample.txt")
    card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT",
        event_type="test_event",
        meta=meta,
        parsed=parsed,
        source_files=["sample.txt"],
        expected_total=3,
    )
    assert card["card_id"] == "RECT_TEST_002_DRAFT"
    assert card["event_type"] == "test_event"
    assert card["status"] == "draft"
    assert card["core_logic"] == ["house_4", "moon"]
    assert len(card["direction_rules"]) == 3
    report = card["draft_import_report"]
    assert report["imported_formula_count"] == 3
    assert report["expected_total"] == 3
    assert report["expected_vs_imported_gap"] == 0
    assert report["explicit_selection_only"] is True
    assert report["production_default_changed"] is False


def test_build_card_forces_draft_status_even_if_meta_tries_to_override() -> None:
    meta = card_io.load_meta_dict(SAMPLE_META)
    parsed = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="s.txt")
    card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT", event_type="test_event", meta=meta, parsed=parsed,
        source_files=["s.txt"], expected_total=3,
    )
    assert card["status"] == "draft"


def test_write_and_read_card_roundtrip(tmp_path: Path) -> None:
    meta = card_io.load_meta_dict(SAMPLE_META)
    parsed = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="s.txt")
    card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT", event_type="test_event", meta=meta, parsed=parsed,
        source_files=["s.txt"], expected_total=3,
    )
    path = card_io.write_card(card, tmp_path)
    assert path == tmp_path / "RECT_TEST_002_DRAFT.json"
    loaded = card_io.read_card("RECT_TEST_002_DRAFT", tmp_path)
    assert loaded == card


def test_read_card_returns_none_when_absent(tmp_path: Path) -> None:
    assert card_io.read_card("RECT_NOPE_002_DRAFT", tmp_path) is None


def test_diff_cards_none_vs_new_reports_all_as_added() -> None:
    meta = card_io.load_meta_dict(SAMPLE_META)
    parsed = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="s.txt")
    new_card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT", event_type="test_event", meta=meta, parsed=parsed,
        source_files=["s.txt"], expected_total=3,
    )
    diff = card_io.diff_cards(None, new_card)
    assert sorted(diff.added_rule_ids) == ["R1", "R2", "R3"]
    assert diff.removed_rule_ids == []
    assert diff.tier_changed == []


def test_diff_cards_detects_added_removed_and_tier_changes() -> None:
    meta = card_io.load_meta_dict(SAMPLE_META)
    old_parsed = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="s.txt")
    old_card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT", event_type="test_event", meta=meta, parsed=old_parsed,
        source_files=["s.txt"], expected_total=3,
    )

    changed_text = SAMPLE_TEXT.replace("Priority: supporting", "Priority: golden") + (
        "\nFormula: Directed Mars -> Natal Pluto\nRule: R4\nAllowed aspects: square\nPriority: context\n"
    )
    new_parsed = parser.parse_formulas(changed_text, meaning="m", comment="c", source_name="s2.txt")
    new_card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT", event_type="test_event", meta=meta, parsed=new_parsed,
        source_files=["s2.txt"], expected_total=4,
    )

    diff = card_io.diff_cards(old_card, new_card)
    assert diff.added_rule_ids == ["R4"]
    assert diff.removed_rule_ids == []
    assert diff.tier_changed == [{"rule_id": "R2", "old_tier": "supporting", "new_tier": "golden"}]


def test_built_card_loads_via_real_formula_card_loader(tmp_path: Path) -> None:
    """Интеграционная проверка: сборка совместима с реальным FormulaCardLoader/FormulaCard."""
    from app.services.rectification_formula.formula_card_loader import FormulaCardLoader

    meta = card_io.load_meta_dict(SAMPLE_META)
    parsed = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="s.txt")
    card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT", event_type="test_event", meta=meta, parsed=parsed,
        source_files=["s.txt"], expected_total=3,
    )
    card_io.write_card(card, tmp_path)

    loader = FormulaCardLoader(cards_root=tmp_path)
    loaded = loader.load_card("RECT_TEST_002_DRAFT")
    assert loaded.status == "draft"
    assert loaded.event_type == "test_event"
    assert len(loaded.direction_rules) == 3
    assert {r.id for r in loaded.direction_rules} == {"R1", "R2", "R3"}


def _write_clean_card(cards_root: Path, card_id: str = "RECT_TEST_002_DRAFT") -> None:
    meta = card_io.load_meta_dict(SAMPLE_META)
    parsed = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="s.txt")
    card = card_io.build_card(
        card_id=card_id, event_type="test_event", meta=meta, parsed=parsed,
        source_files=["s.txt"], expected_total=3,
    )
    card_io.write_card(card, cards_root)


def test_verify_card_ok_for_clean_draft_card(tmp_path: Path) -> None:
    _write_clean_card(tmp_path)
    result = verify.verify_card("RECT_TEST_002_DRAFT", tmp_path)
    assert result.ok is True
    assert result.checks["loads"] is True
    assert result.checks["status_is_draft"] is True
    assert result.checks["counts_match_expected"] is True
    assert result.problems == []


def test_verify_card_fails_when_missing(tmp_path: Path) -> None:
    result = verify.verify_card("RECT_MISSING_002_DRAFT", tmp_path)
    assert result.ok is False
    assert result.checks["loads"] is False


def test_verify_card_flags_non_draft_status(tmp_path: Path) -> None:
    _write_clean_card(tmp_path)
    card = card_io.read_card("RECT_TEST_002_DRAFT", tmp_path)
    card["status"] = "test"
    card_io.write_card(card, tmp_path)
    result = verify.verify_card("RECT_TEST_002_DRAFT", tmp_path)
    assert result.ok is False
    assert result.checks["status_is_draft"] is False
    assert any("draft" in p for p in result.problems)


def test_verify_card_flags_expected_vs_imported_gap(tmp_path: Path) -> None:
    meta = card_io.load_meta_dict(SAMPLE_META)
    parsed = parser.parse_formulas(SAMPLE_TEXT, meaning="m", comment="c", source_name="s.txt")
    card = card_io.build_card(
        card_id="RECT_TEST_002_DRAFT", event_type="test_event", meta=meta, parsed=parsed,
        source_files=["s.txt"], expected_total=99,  # намеренно неверный ожидаемый total
    )
    card_io.write_card(card, tmp_path)
    result = verify.verify_card("RECT_TEST_002_DRAFT", tmp_path)
    assert result.ok is False
    assert result.checks["counts_match_expected"] is False
