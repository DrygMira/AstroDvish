from __future__ import annotations

from datetime import date
from typing import Any

from app.models.event_models import EventCard
from app.models.formula_card_models import FormulaCard, FormulaTestModeResult
from app.models.response_models import ChartResponse
from app.services.rectification_formula.directions_formula_matcher import DirectionsFormulaMatcher
from app.services.rectification_formula.formula_card_loader import FormulaCardLoader


class FormulaTestModeService:
    def __init__(self, loader: FormulaCardLoader | None = None) -> None:
        self.loader = loader or FormulaCardLoader()
        self.directions_matcher = DirectionsFormulaMatcher()

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
        chart = self._extract_chart(context)
        event = self._extract_event(context)
        candidate_birth_date = self._extract_birth_date(context)

        indicators = {str(item) for item in context.get("indicators", [])}
        weak_context = {str(item) for item in context.get("weak_indicators", [])}
        exclusion_context = {str(item) for item in context.get("exclusion_indicators", [])}
        methods_used = self._extract_methods(context)

        matched_formula_aspects = []
        rejected_aspects = []
        missing_formula_links: list[str] = []
        if chart is not None and event is not None and candidate_birth_date is not None and card.direction_rules:
            matched_formula_aspects, rejected_aspects, missing_formula_links = self.directions_matcher.evaluate(
                card=card,
                chart=chart,
                candidate_birth_date=candidate_birth_date,
                event=event,
            )
            indicators.update(self._derived_indicators(matches=matched_formula_aspects))

        matched_core = [item for item in card.core_logic if item in indicators]
        matched_aspects = [item for item in card.aspects if item in indicators]
        matched_strong = [item for item in card.strong_confirmation if item in indicators]
        matched_weak = [item for item in card.weak_confirmation if item in indicators or item in weak_context]
        missing = [item for item in [*card.core_logic, *card.aspects] if item not in indicators]
        exclusion_risks = [item for item in card.exclusions if item in indicators or item in exclusion_context]

        score = 0.0
        score += len(matched_core) * 12.0
        score += len(matched_aspects) * 8.0
        score += len(matched_strong) * 7.0
        score += len(matched_weak) * 3.0
        score += len(matched_formula_aspects) * 4.0
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
            "Это предварительная экспертная проверка, не финальная профессиональная ректификация."
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
            matched_formula_aspects=matched_formula_aspects,
            missing_formula_links=missing_formula_links,
            rejected_aspects=rejected_aspects,
            debug={
                "matched_core": matched_core,
                "matched_aspects": matched_aspects,
                "matched_strong": matched_strong,
                "matched_weak": matched_weak,
                "method_priority": card.method_priority,
                "non_scoring_methods": [item for item in methods_used if item != "directions"],
            },
        )

    @staticmethod
    def _extract_chart(context: dict[str, Any]) -> ChartResponse | None:
        raw = context.get("chart_response") or context.get("chart")
        if raw is None:
            return None
        if isinstance(raw, ChartResponse):
            return raw
        if isinstance(raw, dict):
            return ChartResponse.model_validate(raw)
        return None

    @staticmethod
    def _extract_event(context: dict[str, Any]) -> EventCard | None:
        raw = context.get("event")
        if raw is None:
            return None
        if isinstance(raw, EventCard):
            return raw
        if isinstance(raw, dict):
            return EventCard.model_validate(raw)
        return None

    @staticmethod
    def _extract_birth_date(context: dict[str, Any]) -> date | None:
        raw = context.get("candidate_birth_date")
        if raw is None:
            return None
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            return date.fromisoformat(raw)
        return None

    @staticmethod
    def _derived_indicators(*, matches: list[Any]) -> set[str]:
        derived: set[str] = set()
        if matches:
            derived.add("multiple_methods")

        for rule_id in {str(item.formula_rule_matched) for item in matches}:
            derived.add(rule_id)
        for item in matches:
            directed = str(item.directed_point)
            target = str(item.natal_target)
            if directed.startswith("cusp_5") or target.startswith("cusp_5"):
                derived.add("house_5")
            if directed.startswith("cusp_4") or target.startswith("cusp_4"):
                derived.add("house_4")
            if directed.startswith("ruler_5") or target.startswith("ruler_5"):
                derived.add("ruler_5")
            if "moon" in directed or "moon" in target:
                derived.add("moon")
            if "jupiter" in directed or "jupiter" in target:
                derived.add("jupiter_support")
        if len(matches) >= 2:
            derived.add("family_axis_activation")
            derived.add("angle_link")
            derived.add("ruler_5_angle_link")
        if any(str(item.directed_point).startswith("house_element_5:") for item in matches):
            derived.add("house_5_without_angles")
        return derived

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
        scoring_methods = [item for item in methods_used if item == "directions"]
        if not scoring_methods:
            return 0.0

        total = 0.0
        for idx, method_name in enumerate(method_priority):
            if method_name not in scoring_methods:
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
