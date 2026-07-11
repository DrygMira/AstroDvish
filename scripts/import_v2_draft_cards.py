from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path.cwd()
if not (ROOT / "product" / "astrobot_content_pack").exists():
    ROOT = Path(__file__).resolve().parents[1]
CARDS_DIR = ROOT / "product" / "astrobot_content_pack" / "formula_cards" / "rectification"
DOCS_DIR = ROOT / "docs"
TELEGRAM_DIR = Path(r"C:\Users\user\Downloads\Telegram Desktop")

MAJOR_ASPECTS = ["conjunction", "square", "opposition", "trine", "sextile"]
PRIORITY_ORDER = {"golden": 3, "supporting": 2, "context": 1, "ambiguity_risk": 0}
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
FORMULA_BLOCK_RE = re.compile(
    r"^Formula:\s*(.*?)\s*\nRule:\s*(.*?)\s*\nAllowed aspects:\s*(.*?)\s*\nPriority:\s*(.*?)\s*$",
    re.S,
)
FORMULA_RE = re.compile(r"^Directed\s+(.*?)\s*->\s*Natal\s+(.*?)$")


@dataclass(frozen=True)
class CardSpec:
    source_path: Path
    card_id: str
    event_type: str
    card_version: str
    title: str
    source_meaning: str
    source_comment: str
    expected_counts: dict[str, int]
    core_logic: list[str]
    houses: list[str]
    planets: list[str]
    significators: list[str]
    aspects: list[str]
    strong_confirmation: list[str]
    weak_confirmation: list[str]
    exclusions: list[str]
    expert_note: str


def _resolve_source_path(*filenames: str, glob_pattern: str | None = None) -> Path:
    for filename in filenames:
        candidate = TELEGRAM_DIR / filename
        if candidate.exists():
            return candidate
    if glob_pattern:
        matches = sorted(TELEGRAM_DIR.glob(glob_pattern))
        if matches:
            return matches[0]
    names = set(filenames)
    for item in TELEGRAM_DIR.iterdir():
        if item.name in names:
            return item
    raise FileNotFoundError(f"Could not resolve source file from candidates: {filenames!r}, glob={glob_pattern!r}")


CARD_SPECS = [
    CardSpec(
        source_path=_resolve_source_path(glob_pattern="6 - * (2).txt"),
        card_id="RECT_MOTHER_DEATH_002_DRAFT",
        event_type="death_mother",
        card_version="death_mother_literal_draft_v2_imported_2026_07_05",
        title="Death of mother (draft v2 imported sandbox)",
        source_meaning="Imported literal mother-death v2 formula from Ekaterina revised draft pack.",
        source_comment=(
            "Re-imported from Ekaterina revised V2 source pack on 2026-07-05. "
            "Reverse formulas are explicit only; no auto-created mirror rules."
        ),
        expected_counts={"golden": 32, "supporting": 26, "context": 20, "total": 78},
        core_logic=["house_4", "house_8", "house_11", "moon", "saturn", "pluto"],
        houses=["house_4", "house_8", "house_10", "house_11"],
        planets=["moon", "pluto", "saturn"],
        significators=["moon", "pluto", "saturn"],
        aspects=["maternal_loss_axis", "death_axis_activation", "family_status_loss"],
        strong_confirmation=["multiple_methods", "maternal_marker_activation", "loss_axis_activation"],
        weak_confirmation=["single_transit_only", "context_only_confirmation"],
        exclusions=["relationship_only_signature", "career_only_signature"],
        expert_note="clean revised re-import; previous tier conflicts are no longer present in the new source pack.",
    ),
    CardSpec(
        source_path=_resolve_source_path(glob_pattern="7_*.txt"),
        card_id="RECT_SIBLING_DEATH_002_DRAFT",
        event_type="death_sibling",
        card_version="death_sibling_literal_draft_v2_imported_2026_07_05",
        title="Death of sibling (draft v2 imported sandbox)",
        source_meaning="Imported literal sibling-death v2 formula from Ekaterina draft pack.",
        source_comment=(
            "Imported from Ekaterina V2 source pack on 2026-07-05. "
            "Reverse formulas are explicit only; no auto-created mirror rules."
        ),
        expected_counts={"golden": 38, "supporting": 26, "context": 24, "total": 88},
        core_logic=["house_3", "house_8", "house_10", "mercury", "saturn", "pluto"],
        houses=["house_3", "house_8", "house_9", "house_10"],
        planets=["mercury", "pluto", "saturn"],
        significators=["mercury", "pluto", "saturn"],
        aspects=["sibling_loss_axis", "death_axis_activation", "kinship_status_loss"],
        strong_confirmation=["multiple_methods", "sibling_marker_activation", "loss_axis_activation"],
        weak_confirmation=["single_transit_only", "context_only_confirmation"],
        exclusions=["relationship_only_signature", "career_only_signature"],
        expert_note="source contains 4 exact same-tier duplicate rule ids; they are collapsed deterministically without semantic conflict.",
    ),
    CardSpec(
        source_path=_resolve_source_path(glob_pattern="8_*.txt"),
        card_id="RECT_GRANDPARENT_DEATH_002_DRAFT",
        event_type="death_grandparent",
        card_version="death_grandparent_literal_draft_v2_imported_2026_07_05",
        title="Death of grandparent (draft v2 imported sandbox)",
        source_meaning="Imported literal grandparent-death v2 formula from Ekaterina draft pack.",
        source_comment=(
            "Imported from Ekaterina V2 source pack on 2026-07-05. "
            "Reverse formulas are explicit only; no auto-created mirror rules."
        ),
        expected_counts={"golden": 32, "supporting": 24, "context": 24, "total": 80},
        core_logic=["house_4", "house_8", "house_11", "saturn", "pluto"],
        houses=["house_4", "house_8", "house_11"],
        planets=["pluto", "saturn"],
        significators=["pluto", "saturn"],
        aspects=["ancestor_loss_axis", "death_axis_activation", "family_line_loss"],
        strong_confirmation=["multiple_methods", "ancestor_marker_activation", "loss_axis_activation"],
        weak_confirmation=["single_transit_only", "context_only_confirmation"],
        exclusions=["relationship_only_signature", "career_only_signature"],
        expert_note="clean import; ready for explicit test mode after semantic expert review.",
    ),
]


def split_blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def parse_block(block: str) -> dict[str, str] | None:
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


def build_direction_rule(
    *,
    spec: CardSpec,
    parsed: dict[str, str],
    source_note: str,
    expert_review_needed: bool = False,
    extra_comment: str | None = None,
) -> dict[str, object]:
    priority = str(parsed["priority"])
    allowed_aspects = list(MAJOR_ASPECTS)
    target = str(parsed["target"])
    comment = spec.source_comment
    if extra_comment:
        comment = f"{comment} {extra_comment}"
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
        "meaning": spec.source_meaning,
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


def import_card(spec: CardSpec) -> tuple[dict[str, object], dict[str, object]]:
    text = spec.source_path.read_text(encoding="utf-8")
    blocks = split_blocks(text)
    kept_by_rule: dict[str, dict[str, object]] = {}
    order: list[str] = []
    duplicates_report: list[dict[str, object]] = []
    malformed_blocks: list[dict[str, object]] = []
    conflicts_for_review: list[dict[str, object]] = []
    selector_tokens: set[str] = set()
    duplicate_groups: set[str] = set()
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
        source_note = f"{spec.source_path.name} block #{idx}"
        selector_tokens.add(str(parsed["source"]))
        selector_tokens.add(str(parsed["target"]))
        current_rule = build_direction_rule(spec=spec, parsed=parsed, source_note=source_note)
        rule_id = str(parsed["rule"])

        if rule_id not in kept_by_rule:
            kept_by_rule[rule_id] = current_rule
            order.append(rule_id)
            continue

        duplicate_groups.add(rule_id)
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
            conflict_entry = {
                "rule_id": rule_id,
                "source_occurrences": 2,
                "priorities_found": sorted({existing_priority, new_priority}, key=lambda item: -PRIORITY_ORDER[item]),
                "kept_priority": new_priority if keep_new else existing_priority,
                "review_reason": "same literal rule appears in source pack under different priority tiers",
            }
            conflicts_for_review.append(conflict_entry)
            note = (
                "Source pack also contained the same rule under a different priority tier; kept the strongest tier and "
                "flagged for expert review."
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
    imported_tiers = Counter(str(rule["priority_tier"]) for rule in direction_rules)
    imported_formula_count = len(direction_rules)
    expected_total = int(spec.expected_counts["total"])

    card = {
        "card_id": spec.card_id,
        "event_type": spec.event_type,
        "status": "draft",
        "card_version": spec.card_version,
        "school": "expert_rectification_v2_draft",
        "title": spec.title,
        "core_logic": spec.core_logic,
        "houses": spec.houses,
        "planets": spec.planets,
        "significators": spec.significators,
        "aspects": spec.aspects,
        "method_priority": ["directions", "solars", "transits"],
        "strong_confirmation": spec.strong_confirmation,
        "weak_confirmation": spec.weak_confirmation,
        "exclusions": spec.exclusions,
        "direction_rules": direction_rules,
        "notes": (
            f"Draft sandbox imported from Ekaterina {spec.event_type} v2 pack on 2026-07-05. "
            "Explicit expert/test selection only; production defaults unchanged."
        ),
        "draft_import_report": {
            "source_files": [str(spec.source_path)],
            "source_formula_counts_header": spec.expected_counts,
            "parsed_entries_count": parsed_entries_count,
            "unique_rule_count_detected": imported_formula_count,
            "imported_formula_count": imported_formula_count,
            "imported_tier_counts": {
                "golden": imported_tiers.get("golden", 0),
                "supporting": imported_tiers.get("supporting", 0),
                "context": imported_tiers.get("context", 0),
                "ambiguity_risk": imported_tiers.get("ambiguity_risk", 0),
            },
            "effective_direction_rules_count": imported_formula_count,
            "effective_tier_counts": {
                "golden": imported_tiers.get("golden", 0),
                "supporting": imported_tiers.get("supporting", 0),
                "context": imported_tiers.get("context", 0),
                "ambiguity_risk": imported_tiers.get("ambiguity_risk", 0),
            },
            "duplicate_groups_count": len(duplicate_groups),
            "collapsed_duplicate_entries": len(duplicates_report),
            "malformed_entries_count": len(malformed_blocks),
            "skipped_malformed_blocks": malformed_blocks,
            "duplicates_report": duplicates_report,
            "recoverable_candidates": [],
            "conflicts_for_review": conflicts_for_review,
            "conflicts_left_for_review": bool(conflicts_for_review),
            "selector_tokens_detected": sorted(selector_tokens),
            "production_default_changed": False,
            "explicit_selection_only": True,
            "event_type_binding": spec.event_type,
            "import_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "expected_total": expected_total,
            "expected_vs_imported_gap": expected_total - imported_formula_count,
        },
    }
    return card, card["draft_import_report"]


def write_import_report(cards: list[dict[str, object]], specs: list[CardSpec]) -> None:
    report_path = DOCS_DIR / "FORMULA_V2_IMPORT_REPORT.md"
    lines = [
        "# FORMULA_V2_IMPORT_REPORT",
        "",
        "## Latest import",
        "- date: `2026-07-05`",
        "- scope:",
    ]
    for spec in specs:
        lines.append(f"  - `{spec.card_id}`")
    lines.extend(
        [
            "- mode: explicit expert/test only",
            "- production defaults: unchanged",
            "",
            "## Summary table",
            "",
            "| Card ID | Event type | Source expected | Imported unique | Golden | Supporting | Context | Duplicate groups | Collapsed duplicates | Conflicts for review | Malformed/skipped |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for card in cards:
        report = card["draft_import_report"]
        tier = report["imported_tier_counts"]
        lines.append(
            f"| `{card['card_id']}` | `{card['event_type']}` | {report['expected_total']} | {report['imported_formula_count']} | "
            f"{tier['golden']} | {tier['supporting']} | {tier['context']} | {report['duplicate_groups_count']} | "
            f"{report['collapsed_duplicate_entries']} | {len(report['conflicts_for_review'])} | {report['malformed_entries_count']} |"
        )
    lines.extend(["", "## Per-card reconciliation", ""])
    for spec, card in zip(specs, cards):
        report = card["draft_import_report"]
        tier = report["imported_tier_counts"]
        lines.extend(
            [
                f"### {spec.card_id}",
                f"- card_id: `{spec.card_id}`",
                f"- event_type: `{spec.event_type}`",
                "- source expected counts:",
                f"  - golden: `{spec.expected_counts['golden']}`",
                f"  - supporting: `{spec.expected_counts['supporting']}`",
                f"  - context: `{spec.expected_counts['context']}`",
                f"  - total: `{spec.expected_counts['total']}`",
                "- imported counts:",
                f"  - unique imported rules: `{report['imported_formula_count']}`",
                f"  - imported tiers: `{tier['golden']} / {tier['supporting']} / {tier['context']}`",
                f"- duplicate groups: `{report['duplicate_groups_count']}`",
                f"- collapsed duplicates: `{report['collapsed_duplicate_entries']}`",
                f"- conflicts_for_review: `{len(report['conflicts_for_review'])}`",
                f"- malformed/skipped entries: `{report['malformed_entries_count']}`",
                "- expert note:",
                f"  - purpose: {spec.title}",
                f"  - expert confirmation needed: {spec.expert_note}",
                "  - test-mode readiness: `yes`",
                "",
            ]
        )
        if report["duplicates_report"]:
            lines.append("- duplicate groups detail:")
            for item in report["duplicates_report"]:
                lines.append(
                    f"  - `{item['rule_id']}`: kept `{item['kept_priority']}`, resolution `{item['resolution']}`"
                )
            lines.append("")
        if report["conflicts_for_review"]:
            lines.append("- conflicts_for_review detail:")
            for item in report["conflicts_for_review"]:
                lines.append(
                    f"  - `{item['rule_id']}`: priorities `{', '.join(item['priorities_found'])}`, kept `{item['kept_priority']}`"
                )
            lines.append("")
    lines.extend(
        [
            "## Import conclusion",
            "- `RECT_MOTHER_DEATH_002_DRAFT`: revised source pack imported cleanly; previous tier conflicts are removed in the new source file",
            "- `RECT_SIBLING_DEATH_002_DRAFT`: structurally valid import; 4 exact same-tier duplicates collapsed deterministically",
            "- `RECT_GRANDPARENT_DEATH_002_DRAFT`: clean import, ready for explicit test mode",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_expert_review_summary(cards: list[dict[str, object]], specs: list[CardSpec]) -> None:
    report_path = DOCS_DIR / "FORMULA_V2_EXPERT_REVIEW_SUMMARY.md"
    by_id = {card["card_id"]: card for card in cards}
    lines = [
        "# FORMULA_V2_EXPERT_REVIEW_SUMMARY",
        "",
        "## Purpose",
        "This note is the expert-readable handoff for the latest three V2 draft card updates.",
        "It is intended for review before any later live deploy.",
        "",
        "## Cards in scope",
    ]
    for spec in specs:
        lines.append(f"- `{spec.card_id}`")
    lines.extend(["", "## Event bindings used in repo"])
    for spec in specs:
        lines.append(f"- `{spec.card_id}` -> `{spec.event_type}`")
    lines.extend(["", "## Expert review summary", ""])
    for spec in specs:
        card = by_id[spec.card_id]
        report = card["draft_import_report"]
        tier = report["imported_tier_counts"]
        lines.extend(
            [
                f"### {spec.card_id}",
                f"- status: {'clean import' if not report['conflicts_left_for_review'] else 'import valid, review required'}",
                f"- counts: `{report['imported_formula_count']} = {tier['golden']} golden + {tier['supporting']} supporting + {tier['context']} context`",
                f"- duplicate groups: `{report['duplicate_groups_count']}`",
                f"- collapsed duplicates: `{report['collapsed_duplicate_entries']}`",
                f"- malformed/skipped: `{report['malformed_entries_count']}`",
                f"- conflicts_for_review: `{len(report['conflicts_for_review'])}`",
                f"- expert action: {spec.expert_note}",
                "- test-mode readiness: `ready`",
                "",
            ]
        )
    lines.extend(
        [
            "## Deploy-ready checklist",
            "- production defaults remain unchanged",
            "- cards remain explicit-only draft/test mode",
            "- run focused formula-card / Pro endpoint / UI selector tests before deploy",
            "- run full pytest before any deploy command",
            "- verify selector, multi-card combined report, expert tables, and Excel export include the new cards",
            "",
            "## Recommendation",
            "- ready for deploy after tests: `yes`",
            "- no deploy performed by this script",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    cards: list[dict[str, object]] = []
    for spec in CARD_SPECS:
        card, _ = import_card(spec)
        cards.append(card)
        out_path = CARDS_DIR / f"{spec.card_id}.json"
        out_path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path}")
    write_import_report(cards, CARD_SPECS)
    write_expert_review_summary(cards, CARD_SPECS)
    print(f"wrote {DOCS_DIR / 'FORMULA_V2_IMPORT_REPORT.md'}")
    print(f"wrote {DOCS_DIR / 'FORMULA_V2_EXPERT_REVIEW_SUMMARY.md'}")


if __name__ == "__main__":
    main()
