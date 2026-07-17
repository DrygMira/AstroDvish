"""Чистый парсинг txt-пака формул (Екатерина) в direction_rules (без сети, без CardSpec).

Формат исходного блока (устоявшийся, см. docs/FORMULA_V2_IMPORT_REPORT.md):
    Formula: Directed <planet/point> -> Natal <planet/point>
    Rule: <rule id>
    Allowed aspects: <aspect>, <aspect>, ...
    Priority: golden|supporting|context|ambiguity_risk
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

MAJOR_ASPECTS = ["conjunction", "square", "opposition", "trine", "sextile"]
PRIORITY_ORDER = {"golden": 3, "supporting": 2, "context": 1, "ambiguity_risk": 0}

FORMULA_BLOCK_RE = re.compile(
    r"^Formula:\s*(.*?)\s*\nRule:\s*(.*?)\s*\nAllowed aspects:\s*(.*?)\s*\nPriority:\s*(.*?)\s*$",
    re.S,
)
FORMULA_RE = re.compile(r"^Directed\s+(.*?)\s*->\s*Natal\s+(.*?)$")


def split_blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def parse_block(block: str) -> dict[str, object] | None:
    match = FORMULA_BLOCK_RE.match(block)
    if not match:
        return None
    formula, rule, aspects, priority = [item.strip() for item in match.groups()]
    formula_match = FORMULA_RE.match(formula)
    if not formula_match:
        return None
    source, target = [item.strip() for item in formula_match.groups()]
    allowed_aspects = [item.strip().lower() for item in aspects.split(",") if item.strip()]
    return {
        "formula": formula,
        "rule": rule,
        "source": source,
        "target": target,
        "allowed_aspects": allowed_aspects,
        "priority": priority.strip().lower(),
    }


PLANET_LABELS = {
    "sun": "Sun",
    "moon": "Moon",
    "mercury": "Mercury",
    "venus": "Venus",
    "mars": "Mars",
    "jupiter": "Jupiter",
    "saturn": "Saturn",
    "uranus": "Uranus",
    "neptune": "Neptune",
    "pluto": "Pluto",
    "chiron": "Chiron",
}


def build_direction_rule(
    *,
    parsed: dict[str, object],
    meaning: str,
    comment: str,
    source_note: str,
    expert_review_needed: bool = False,
) -> dict[str, object]:
    priority = str(parsed["priority"])
    allowed_aspects = list(MAJOR_ASPECTS)
    target = str(parsed["target"])
    return {
        "id": parsed["rule"],
        "title": parsed["formula"],
        "formula": parsed["formula"],
        "rule": parsed["rule"],
        "source": parsed["source"],
        "source_layer": "directed",
        "target": target,
        "target_layer": "natal",
        "allowed_aspects": allowed_aspects,
        "aspect": allowed_aspects[0] if allowed_aspects else "conjunction",
        "priority": priority,
        "role": "context" if priority == "context" else "event_confirmation",
        "meaning": meaning,
        "comment": comment,
        "expert_review_needed": expert_review_needed,
        "source_note": source_note,
        "source_kind": "directed",
        "target_kind": "natal",
        "source_selectors": [parsed["source"]],
        "target_selectors": [target],
        "display_source": parsed["source"],
        "display_target": PLANET_LABELS.get(target, target),
        "aspect_types": allowed_aspects,
        "orb_limit": 1.0,
        "required": priority != "context",
        "weight": 1.4 if priority == "golden" else 1.0 if priority == "supporting" else 0.35,
        "priority_tier": priority,
    }


@dataclass
class ParsedFormulas:
    direction_rules: list[dict[str, object]] = field(default_factory=list)
    tier_counts: dict[str, int] = field(default_factory=dict)
    duplicates_report: list[dict[str, object]] = field(default_factory=list)
    malformed_blocks: list[dict[str, object]] = field(default_factory=list)
    conflicts_for_review: list[dict[str, object]] = field(default_factory=list)
    parsed_entries_count: int = 0

    @property
    def imported_formula_count(self) -> int:
        return len(self.direction_rules)


def parse_formulas(text: str, *, meaning: str, comment: str, source_name: str) -> ParsedFormulas:
    """Разобрать txt-пак формул в уникальные direction_rules с разрешением конфликтов тиров.

    Правило разрешения дублей: одинаковый rule id, разные тиры -> оставляем более
    сильный тир и флагим на expert review (см. PRIORITY_ORDER). Одинаковый тир,
    разная формула -> оставляем первую (kept_first_same_priority_duplicate).
    """
    blocks = split_blocks(text)
    kept_by_rule: dict[str, dict[str, object]] = {}
    order: list[str] = []
    duplicates_report: list[dict[str, object]] = []
    malformed_blocks: list[dict[str, object]] = []
    conflicts_for_review: list[dict[str, object]] = []
    parsed_entries_count = 0

    for idx, block in enumerate(blocks, start=1):
        parsed = parse_block(block)
        if parsed is None:
            malformed_blocks.append(
                {
                    "block_index": idx,
                    "preview": block.splitlines()[:4],
                    "reason": "formula/rule/aspects/priority block did not match expected literal format",
                }
            )
            continue

        parsed_entries_count += 1
        source_note = f"{source_name} block #{idx}"
        current_rule = build_direction_rule(parsed=parsed, meaning=meaning, comment=comment, source_note=source_note)
        rule_id = str(parsed["rule"])

        if rule_id not in kept_by_rule:
            kept_by_rule[rule_id] = current_rule
            order.append(rule_id)
            continue

        existing = kept_by_rule[rule_id]
        existing_priority = str(existing["priority_tier"])
        new_priority = str(parsed["priority"])
        resolution = "kept_first_exact_duplicate"
        keep_new = False
        if PRIORITY_ORDER[new_priority] > PRIORITY_ORDER[existing_priority]:
            keep_new = True
            resolution = "replaced_lower_priority_duplicate"
        elif PRIORITY_ORDER[new_priority] < PRIORITY_ORDER[existing_priority]:
            resolution = "kept_higher_priority_duplicate"
        elif parsed["formula"] != existing["formula"]:
            resolution = "kept_first_same_priority_duplicate"

        duplicates_report.append(
            {
                "rule_id": rule_id,
                "kept_formula": parsed["formula"] if keep_new else existing["formula"],
                "kept_priority": new_priority if keep_new else existing_priority,
                "skipped_formula": existing["formula"] if keep_new else parsed["formula"],
                "skipped_priority": existing_priority if keep_new else new_priority,
                "resolution": resolution,
            }
        )

        if new_priority != existing_priority:
            conflicts_for_review.append(
                {
                    "rule_id": rule_id,
                    "priorities_found": sorted({existing_priority, new_priority}, key=lambda item: -PRIORITY_ORDER[item]),
                    "kept_priority": new_priority if keep_new else existing_priority,
                    "review_reason": "same literal rule appears in source pack under different priority tiers",
                }
            )
            note = (
                "Source pack also contained the same rule under a different priority tier; kept the strongest tier "
                "and flagged for expert review."
            )
            if keep_new:
                current_rule["expert_review_needed"] = True
                current_rule["comment"] = f"{current_rule['comment']} {note}"
                kept_by_rule[rule_id] = current_rule
            else:
                existing["expert_review_needed"] = True
                existing["comment"] = f"{existing['comment']} {note}"
        elif keep_new:
            kept_by_rule[rule_id] = current_rule

    direction_rules = [kept_by_rule[rule_id] for rule_id in order]
    tier_counts = Counter(str(rule["priority_tier"]) for rule in direction_rules)

    return ParsedFormulas(
        direction_rules=direction_rules,
        tier_counts={
            "golden": tier_counts.get("golden", 0),
            "supporting": tier_counts.get("supporting", 0),
            "context": tier_counts.get("context", 0),
            "ambiguity_risk": tier_counts.get("ambiguity_risk", 0),
        },
        duplicates_report=duplicates_report,
        malformed_blocks=malformed_blocks,
        conflicts_for_review=conflicts_for_review,
        parsed_entries_count=parsed_entries_count,
    )
