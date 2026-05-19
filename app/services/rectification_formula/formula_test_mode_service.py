from __future__ import annotations

from typing import Any

from app.models.formula_card_models import FormulaCard, FormulaTestModeResult
from app.services.rectification_formula.formula_card_loader import FormulaCardLoader


class FormulaTestModeService:
    def __init__(self, loader: FormulaCardLoader | None = None) -> None:
        self.loader = loader or FormulaCardLoader()

    def evaluate(
        self,
        *,
        event_type: str,
        context: dict[str, Any],
        card_id: str | None = None,
    ) -> dict[str, Any]:
        cards = [self.loader.load_card(card_id)] if card_id else self.loader.load_by_event_type(event_type)
        if not cards:
            raise ValueError(f"no formula cards configured for event_type={event_type}")

        best_result: FormulaTestModeResult | None = None
        for card in cards:
            result = self._evaluate_card(card=card, context=context)
            if best_result is None or result.score > best_result.score:
                best_result = result

        assert best_result is not None
        return best_result.model_dump(mode="json")

    def _evaluate_card(self, *, card: FormulaCard, context: dict[str, Any]) -> FormulaTestModeResult:
        indicators = {str(item) for item in context.get("indicators", [])}
        weak_context = {str(item) for item in context.get("weak_indicators", [])}
        exclusion_context = {str(item) for item in context.get("exclusion_indicators", [])}
        methods_used = self._extract_methods(context)

        matched_core = [item for item in card.core_logic if item in indicators]
        matched_aspects = [item for item in card.aspects if item in indicators]
        matched_strong = [item for item in card.strong_confirmation if item in indicators]
        matched_weak = [
            item for item in card.weak_confirmation if item in indicators or item in weak_context
        ]
        missing = [
            item
            for item in [*card.core_logic, *card.aspects]
            if item not in indicators
        ]
        exclusion_risks = [
            item
            for item in card.exclusions
            if item in indicators or item in exclusion_context
        ]

        score = 0.0
        score += len(matched_core) * 12.0
        score += len(matched_aspects) * 8.0
        score += len(matched_strong) * 7.0
        score += len(matched_weak) * 3.0
        score += self._score_methods(card.method_priority, methods_used)
        score -= len(exclusion_risks) * 10.0
        score = max(0.0, round(score, 1))

        confidence = self._confidence_for(
            score=score,
            matched_core_count=len(matched_core),
            methods_used=methods_used,
            exclusion_risks=exclusion_risks,
        )

        explanation = (
            f"Тестовая карточка {card.card_id} проверена в безопасном режиме. "
            f"Совпали ключевые индикаторы: {', '.join(matched_core + matched_aspects + matched_strong) or 'нет'}. "
            f"Методы с сигналами: {', '.join(methods_used) or 'не указаны'}. "
            f"Это предварительная экспертная проверка, не финальная профессиональная ректификация."
        )

        return FormulaTestModeResult(
            card_id=card.card_id,
            event_type=card.event_type,
            status=card.status,
            matched_indicators=[*matched_core, *matched_aspects, *matched_strong],
            missing_indicators=missing,
            weak_indicators=matched_weak,
            exclusion_risks=exclusion_risks,
            methods_used=methods_used,
            score=score,
            confidence=confidence,
            explanation_for_expert=explanation,
            debug={
                "matched_core": matched_core,
                "matched_aspects": matched_aspects,
                "matched_strong": matched_strong,
                "matched_weak": matched_weak,
                "method_priority": card.method_priority,
            },
        )

    @staticmethod
    def _extract_methods(context: dict[str, Any]) -> list[str]:
        explicit = [str(item) for item in context.get("methods_used", [])]
        if explicit:
            return sorted(dict.fromkeys(explicit))

        pro_result = context.get("pro_result") or {}
        method_results = pro_result.get("method_results") or {}
        methods = [str(name) for name, matches in method_results.items() if matches]
        return sorted(dict.fromkeys(methods))

    @staticmethod
    def _score_methods(method_priority: list[str], methods_used: list[str]) -> float:
        if not methods_used:
            return 0.0
        total = 0.0
        for idx, method_name in enumerate(method_priority):
            if method_name not in methods_used:
                continue
            total += max(2.0, 8.0 - (idx * 2.0))
        return total

    @staticmethod
    def _confidence_for(
        *,
        score: float,
        matched_core_count: int,
        methods_used: list[str],
        exclusion_risks: list[str],
    ) -> str:
        if score >= 60 and matched_core_count >= 3 and len(methods_used) >= 2 and not exclusion_risks:
            return "high"
        if score >= 35 and matched_core_count >= 2:
            return "medium"
        return "low"
