"""Сборка/чтение/запись/diff формула-карточек (draft, explicit-only) — без сети."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts.cardlib.parser import ParsedFormulas

REQUIRED_META_FIELDS = (
    "title",
    "source_meaning",
    "source_comment",
    "core_logic",
    "houses",
    "planets",
    "significators",
    "aspects",
    "strong_confirmation",
    "weak_confirmation",
    "exclusions",
    "expert_note",
)


class CardMetaError(ValueError):
    pass


@dataclass(frozen=True)
class CardMeta:
    title: str
    source_meaning: str
    source_comment: str
    core_logic: list[str]
    houses: list[str]
    planets: list[str]
    significators: list[str]
    aspects: list[str]
    strong_confirmation: list[str]
    weak_confirmation: list[str]
    exclusions: list[str]
    expert_note: str


def load_meta_dict(raw: dict[str, object]) -> CardMeta:
    missing = [name for name in REQUIRED_META_FIELDS if name not in raw]
    if missing:
        raise CardMetaError(f"meta missing required fields: {', '.join(missing)}")
    return CardMeta(**{name: raw[name] for name in REQUIRED_META_FIELDS})


def load_meta(path: Path) -> CardMeta:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CardMetaError(f"{path}: invalid JSON: {exc}") from exc
    return load_meta_dict(raw)


def build_card(
    *,
    card_id: str,
    event_type: str,
    meta: CardMeta,
    parsed: ParsedFormulas,
    source_files: list[str],
    expected_total: int,
    card_version: str | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    """Собрать FormulaCard-совместимый dict. status форсированно 'draft' (explicit-only)."""
    imported_count = parsed.imported_formula_count
    return {
        "card_id": card_id,
        "event_type": event_type,
        "status": "draft",
        "card_version": card_version or f"{event_type}_v2_draft_{datetime.now(timezone.utc):%Y_%m_%d}",
        "school": "expert_rectification_v2_draft",
        "title": meta.title,
        "core_logic": list(meta.core_logic),
        "houses": list(meta.houses),
        "planets": list(meta.planets),
        "significators": list(meta.significators),
        "aspects": list(meta.aspects),
        "method_priority": ["directions", "solars", "transits"],
        "strong_confirmation": list(meta.strong_confirmation),
        "weak_confirmation": list(meta.weak_confirmation),
        "exclusions": list(meta.exclusions),
        "direction_rules": parsed.direction_rules,
        "notes": notes or (
            f"Draft sandbox card for {event_type}, built with scripts/card_tool.py. "
            "Explicit expert/test selection only; production defaults unchanged."
        ),
        "draft_import_report": {
            "source_files": source_files,
            "parsed_entries_count": parsed.parsed_entries_count,
            "imported_formula_count": imported_count,
            "imported_tier_counts": dict(parsed.tier_counts),
            "duplicate_groups_count": len(parsed.duplicates_report),
            "collapsed_duplicate_entries": len(parsed.duplicates_report),
            "malformed_entries_count": len(parsed.malformed_blocks),
            "skipped_malformed_blocks": parsed.malformed_blocks,
            "duplicates_report": parsed.duplicates_report,
            "conflicts_for_review": parsed.conflicts_for_review,
            "conflicts_left_for_review": bool(parsed.conflicts_for_review),
            "production_default_changed": False,
            "explicit_selection_only": True,
            "event_type_binding": event_type,
            "import_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "expected_total": expected_total,
            "expected_vs_imported_gap": expected_total - imported_count,
        },
    }


def write_card(card: dict[str, object], cards_root: Path) -> Path:
    cards_root.mkdir(parents=True, exist_ok=True)
    path = cards_root / f"{card['card_id']}.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_card(card_id: str, cards_root: Path) -> dict[str, object] | None:
    path = cards_root / f"{card_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class CardDiff:
    added_rule_ids: list[str] = field(default_factory=list)
    removed_rule_ids: list[str] = field(default_factory=list)
    tier_changed: list[dict[str, str]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added_rule_ids or self.removed_rule_ids or self.tier_changed)


def diff_cards(old_card: dict[str, object] | None, new_card: dict[str, object]) -> CardDiff:
    """Diff между старой (уже на диске) и новой версией карточки при переимпорте."""
    new_rules = {str(r["id"]): r for r in new_card["direction_rules"]}
    if old_card is None:
        return CardDiff(added_rule_ids=sorted(new_rules), removed_rule_ids=[], tier_changed=[])

    old_rules = {str(r["id"]): r for r in old_card["direction_rules"]}
    added = sorted(set(new_rules) - set(old_rules))
    removed = sorted(set(old_rules) - set(new_rules))
    tier_changed = []
    for rule_id in sorted(set(new_rules) & set(old_rules)):
        old_tier = str(old_rules[rule_id]["priority_tier"])
        new_tier = str(new_rules[rule_id]["priority_tier"])
        if old_tier != new_tier:
            tier_changed.append({"rule_id": rule_id, "old_tier": old_tier, "new_tier": new_tier})
    return CardDiff(added_rule_ids=added, removed_rule_ids=removed, tier_changed=tier_changed)
