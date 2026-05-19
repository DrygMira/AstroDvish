from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.models.formula_card_models import FormulaCard


class FormulaCardValidationError(ValueError):
    pass


class FormulaCardLoader:
    REQUIRED_FIELDS = {
        "card_id",
        "event_type",
        "status",
        "core_logic",
        "aspects",
        "method_priority",
    }

    def __init__(self, cards_root: Path | None = None) -> None:
        self.cards_root = cards_root or (
            Path(__file__).resolve().parents[3] / "product" / "astrobot_content_pack" / "formula_cards" / "rectification"
        )

    def list_cards(self) -> list[FormulaCard]:
        cards: list[FormulaCard] = []
        for path in sorted(self.cards_root.glob("*.json")):
            cards.append(self._load_path(path))
        return cards

    def load_card(self, card_id: str) -> FormulaCard:
        for card in self.list_cards():
            if card.card_id == card_id:
                return card
        raise FormulaCardValidationError(f"formula card not found: {card_id}")

    def load_by_event_type(self, event_type: str) -> list[FormulaCard]:
        return [card for card in self.list_cards() if card.event_type == event_type]

    def _load_path(self, path: Path) -> FormulaCard:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FormulaCardValidationError(f"{path.name}: invalid JSON: {exc}") from exc

        missing = sorted(self.REQUIRED_FIELDS - set(raw))
        if missing:
            joined = ", ".join(missing)
            raise FormulaCardValidationError(f"{path.name}: missing required fields: {joined}")

        try:
            return FormulaCard.model_validate(raw)
        except ValidationError as exc:
            raise FormulaCardValidationError(f"{path.name}: {exc}") from exc
