from __future__ import annotations

from pathlib import Path

import pytest

from scripts.cardlib import parser


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
