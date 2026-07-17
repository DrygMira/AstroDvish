"""Статические проверки формула-карточки: структура + explicit-only инвариант (без сети)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.rectification_formula.formula_card_loader import (
    FormulaCardLoader,
    FormulaCardValidationError,
)
from scripts.cardlib import card_io


@dataclass
class VerifyResult:
    card_id: str
    ok: bool
    checks: dict[str, bool] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def verify_card(card_id: str, cards_root: Path) -> VerifyResult:
    """Проверить карточку локально: грузится ли, draft ли, сходятся ли счётчики импорта."""
    checks: dict[str, bool] = {}
    problems: list[str] = []

    loader = FormulaCardLoader(cards_root=cards_root)
    try:
        card = loader.load_card(card_id)
    except FormulaCardValidationError as exc:
        return VerifyResult(card_id=card_id, ok=False, checks={"loads": False}, problems=[str(exc)])
    checks["loads"] = True

    is_draft = card.status == "draft"
    checks["status_is_draft"] = is_draft
    if not is_draft:
        problems.append(f"status={card.status!r}, ожидался 'draft' (explicit-only инвариант нарушен)")

    raw = card_io.read_card(card_id, cards_root) or {}
    report = raw.get("draft_import_report") or {}
    gap = report.get("expected_vs_imported_gap")
    counts_match = gap == 0
    checks["counts_match_expected"] = counts_match
    if not counts_match:
        problems.append(
            f"expected_vs_imported_gap={gap!r} (ожидалось 0): imported={report.get('imported_formula_count')}, "
            f"expected_total={report.get('expected_total')}"
        )

    conflicts = report.get("conflicts_for_review") or []
    checks["no_unreviewed_conflicts"] = not conflicts
    if conflicts:
        problems.append(f"{len(conflicts)} конфликт(ов) тиров ждут экспертной проверки: {[c['rule_id'] for c in conflicts]}")

    ok = all(checks.values())
    return VerifyResult(card_id=card_id, ok=ok, checks=checks, problems=problems)
