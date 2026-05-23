from __future__ import annotations

from datetime import date
from typing import Any

from app.models.event_models import EventCard
from app.models.formula_card_models import FormulaCard, FormulaTestModeResult
from app.models.response_models import ChartResponse
from app.services.ephemeris_service import EphemerisService
from app.services.rectification_formula.direction_chart_builder import DirectionChartBuilder, DirectionMethod
from app.services.rectification_formula.directions_formula_matcher import DirectionsFormulaMatcher
from app.services.rectification_formula.formula_card_loader import FormulaCardLoader

MVP_SCORING_ASPECTS = {"conjunction", "opposition", "square", "trine", "sextile"}
DEBUG_OPTIONAL_ASPECTS = {"quincunx"}


class FormulaTestModeService:
    def __init__(
        self,
        loader: FormulaCardLoader | None = None,
        ephemeris_service: EphemerisService | None = None,
        default_direction_method: DirectionMethod | None = None,
    ) -> None:
        self.loader = loader or FormulaCardLoader()
        self.default_direction_method: DirectionMethod = default_direction_method or "symbolic_1deg_per_year"
        self.directions_matcher = DirectionsFormulaMatcher(
            direction_chart_builder=DirectionChartBuilder(
                ephemeris_service=ephemeris_service,
                default_method=self.default_direction_method,
            )
        )

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
        direction_method = self._extract_direction_method(context) or self.default_direction_method

        matched_formula_aspects = []
        rejected_aspects = []
        missing_formula_links: list[dict[str, Any]] = []
        rule_debug: list[dict[str, Any]] = []
        if chart is not None and event is not None and candidate_birth_date is not None and card.direction_rules:
            matched_formula_aspects, rejected_aspects, missing_formula_links, rule_debug = self.directions_matcher.evaluate(
                card=card,
                chart=chart,
                candidate_birth_date=candidate_birth_date,
                event=event,
                direction_method=direction_method,
            )
            indicators.update(self._derived_indicators(matches=matched_formula_aspects))

        matched_core = [item for item in card.core_logic if item in indicators]
        matched_aspects = [item for item in card.aspects if item in indicators]
        matched_strong = [item for item in card.strong_confirmation if item in indicators]
        matched_weak = [item for item in card.weak_confirmation if item in indicators or item in weak_context]
        missing = [item for item in [*card.core_logic, *card.aspects] if item not in indicators]
        exclusion_risks = [item for item in card.exclusions if item in indicators or item in exclusion_context]

        score_breakdown = self._score_breakdown(
            card=card,
            matched_core=matched_core,
            matched_aspects=matched_aspects,
            matched_strong=matched_strong,
            matched_weak=matched_weak,
            matched_formula_aspects=matched_formula_aspects,
            methods_used=methods_used,
            exclusion_risks=exclusion_risks,
        )
        score = max(
            0.0,
            round(
                score_breakdown["matched_core_points"]
                + score_breakdown["matched_aspect_points"]
                + score_breakdown["matched_strong_points"]
                + score_breakdown["matched_weak_points"]
                + score_breakdown["matched_formula_aspect_points"]
                + score_breakdown["method_points"]
                - score_breakdown["exclusion_penalty"],
                1,
            ),
        )

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

        validation_report = self._build_validation_report(
            card=card,
            event_type=card.event_type,
            matched_formula_aspects=matched_formula_aspects,
            missing_formula_links=missing_formula_links,
            rejected_aspects=rejected_aspects,
            methods_used=methods_used,
            matched_core=matched_core,
            matched_aspects=matched_aspects,
            matched_strong=matched_strong,
            matched_weak=matched_weak,
            exclusion_risks=exclusion_risks,
            score_breakdown=score_breakdown,
            rule_debug=rule_debug,
        )

        directed_points_debug = self._build_directed_points_debug(rule_debug)
        natal_targets_debug = self._build_natal_targets_debug(rule_debug)

        return FormulaTestModeResult(
            card_id=card.card_id,
            event_type=card.event_type,
            status=card.status,
            card_version=card.card_version,
            card_hash=card.card_hash,
            source_file_path=card.source_file_path,
            source_event_id=event.event_id if event is not None else None,
            source_event_type=event.event_type.value if event is not None else None,
            source_event_title=event.title if event is not None else None,
            source_event_date=(event.date_text or event.start_date) if event is not None else None,
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
            validation_report=validation_report,
            validation_report_table=self._format_validation_report_table(validation_report),
            debug={
                "card_version": card.card_version,
                "card_hash": card.card_hash,
                "source_file_path": card.source_file_path,
                "directed_points_debug": directed_points_debug,
                "natal_targets_debug": natal_targets_debug,
                "matched_core": matched_core,
                "matched_aspects": matched_aspects,
                "matched_strong": matched_strong,
                "matched_weak": matched_weak,
                "method_priority": card.method_priority,
                "direction_method": direction_method,
                "direction_method_label": (
                    "symbolic age arc / 1° per year"
                    if direction_method == "symbolic_1deg_per_year"
                    else "solar arc progressed sun"
                ),
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
    def _extract_direction_method(context: dict[str, Any]) -> DirectionMethod | None:
        raw = context.get("direction_method")
        if raw in {"symbolic_1deg_per_year", "solar_arc"}:
            return raw
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

    @classmethod
    def _score_breakdown(
        cls,
        *,
        card: FormulaCard,
        matched_core: list[str],
        matched_aspects: list[str],
        matched_strong: list[str],
        matched_weak: list[str],
        matched_formula_aspects: list[Any],
        methods_used: list[str],
        exclusion_risks: list[str],
    ) -> dict[str, float]:
        scoring_formula_aspects = [
            item
            for item in matched_formula_aspects
            if str(getattr(item, "aspect_type", "")).lower() in MVP_SCORING_ASPECTS
        ]
        debug_optional_formula_aspects = [
            item
            for item in matched_formula_aspects
            if str(getattr(item, "aspect_type", "")).lower() in DEBUG_OPTIONAL_ASPECTS
        ]
        return {
            "matched_core_points": len(matched_core) * 12.0,
            "matched_aspect_points": len(matched_aspects) * 8.0,
            "matched_strong_points": len(matched_strong) * 7.0,
            "matched_weak_points": len(matched_weak) * 3.0,
            "matched_formula_aspect_points": len(scoring_formula_aspects) * 4.0,
            "debug_optional_formula_aspect_points": 0.0,
            "debug_optional_formula_aspect_count": float(len(debug_optional_formula_aspects)),
            "method_points": cls._score_methods(card.method_priority, methods_used),
            "exclusion_penalty": len(exclusion_risks) * 10.0,
        }

    @classmethod
    def _build_validation_report(
        cls,
        *,
        card: FormulaCard,
        event_type: str,
        matched_formula_aspects: list[Any],
        missing_formula_links: list[dict[str, Any]],
        rejected_aspects: list[Any],
        methods_used: list[str],
        matched_core: list[str],
        matched_aspects: list[str],
        matched_strong: list[str],
        matched_weak: list[str],
        exclusion_risks: list[str],
        score_breakdown: dict[str, float],
        rule_debug: list[dict[str, Any]],
    ) -> dict[str, Any]:
        found = [item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item) for item in matched_formula_aspects]
        rejected = []
        for item in rejected_aspects:
            payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
            payload["reason"] = payload.get("rejection_reason") or "over_orb"
            rejected.append(payload)

        required_rule_ids = {rule.id for rule in card.direction_rules if rule.required}
        suspicious = [
            item for item in found
            if item.get("strength") == "weak"
            or item.get("formula_rule_matched") not in required_rule_ids
            or item.get("aspect_type") in DEBUG_OPTIONAL_ASPECTS
        ]
        final_status = cls._final_status(
            found_count=len(found),
            missed_count=len(missing_formula_links),
            rejected_count=len(rejected),
            suspicious_count=len(suspicious),
        )
        return {
            "event_type": event_type,
            "card_id": card.card_id,
            "card_version": card.card_version,
            "card_hash": card.card_hash,
            "source_file_path": card.source_file_path,
            "expected_by_card": {
                "card_version": card.card_version,
                "card_hash": card.card_hash,
                "source_file_path": card.source_file_path,
                "core_logic": card.core_logic,
                "houses": card.houses,
                "planets": card.planets,
                "significators": card.significators,
                "direction_rules": [
                    {
                        **rule.model_dump(mode="json"),
                        "display_formula": cls._display_formula(rule),
                    }
                    for rule in card.direction_rules
                ],
                "aspects": card.aspects,
            },
            "found_by_engine": found,
            "missed_by_engine": list(missing_formula_links),
            "rejected_aspects": rejected,
            "extra_or_suspicious_aspects": suspicious,
            "score_breakdown": score_breakdown,
            "rule_debug": rule_debug,
            "directed_points_debug": cls._build_directed_points_debug(rule_debug),
            "natal_targets_debug": cls._build_natal_targets_debug(rule_debug),
            "method_scope": {
                "scoring_methods": ["directions"],
                "mvp_direction_method": "symbolic_1deg_per_year",
                "mvp_direction_method_label": "symbolic age arc / 1° per year",
                "optional_debug_direction_methods": ["solar_arc"],
                "debug_only_methods": [item for item in methods_used if item != "directions"],
                "scoring_aspects": sorted(MVP_SCORING_ASPECTS),
                "debug_optional_aspects": sorted(DEBUG_OPTIONAL_ASPECTS),
            },
            "final_status_for_expert": final_status,
            "questions_for_ekaterina": cls._questions_for_expert(
                missing_formula_links=missing_formula_links,
                rejected_aspects=rejected,
                suspicious=suspicious,
                matched_core=matched_core,
                matched_aspects=matched_aspects,
                matched_strong=matched_strong,
                matched_weak=matched_weak,
                exclusion_risks=exclusion_risks,
            ),
        }

    @staticmethod
    def _final_status(*, found_count: int, missed_count: int, rejected_count: int, suspicious_count: int) -> str:
        if found_count == 0:
            return "miss"
        if suspicious_count > 0 or rejected_count > 0:
            return "needs_expert_review"
        if missed_count > 0:
            return "partial"
        return "hit"

    @staticmethod
    def _questions_for_expert(
        *,
        missing_formula_links: list[dict[str, Any]],
        rejected_aspects: list[dict[str, Any]],
        suspicious: list[dict[str, Any]],
        matched_core: list[str],
        matched_aspects: list[str],
        matched_strong: list[str],
        matched_weak: list[str],
        exclusion_risks: list[str],
    ) -> list[str]:
        questions: list[str] = []
        if missing_formula_links:
            labels = [str(item.get("rule_id") or item.get("display_formula") or "unknown_rule") for item in missing_formula_links]
            questions.append(f"Проверить пропущенные обязательные связи: {', '.join(labels)}.")
        if rejected_aspects:
            questions.append("Проверить, допустим ли больший орбис для отклонённых аспектов.")
        if suspicious:
            questions.append("Проверить, считать ли слабые или необязательные связи рабочими.")
        if matched_weak and not matched_strong:
            questions.append("Уточнить, достаточно ли только слабых подтверждений для этой формулы.")
        if exclusion_risks:
            questions.append("Проверить, не объясняется ли событие лучше исключающей категорией.")
        return questions

    @staticmethod
    def _build_directed_points_debug(rule_debug: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points: dict[str, dict[str, Any]] = {}
        for rule in rule_debug:
            direction_arc = rule.get("direction_arc")
            for pair in rule.get("checked_pairs", []):
                point_name = pair.get("directed_point")
                if not point_name:
                    continue
                points[point_name] = {
                    "point_name": point_name,
                    "natal_longitude": pair.get("source_natal_coordinate"),
                    "directed_longitude": pair.get("directed_coordinate"),
                    "direction_arc": direction_arc,
                }
        return list(points.values())

    @staticmethod
    def _build_natal_targets_debug(rule_debug: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points: dict[str, dict[str, Any]] = {}
        for rule in rule_debug:
            for pair in rule.get("checked_pairs", []):
                point_name = pair.get("natal_target")
                if not point_name:
                    continue
                points[point_name] = {
                    "point_name": point_name,
                    "natal_longitude": pair.get("natal_coordinate"),
                }
        return list(points.values())

    @staticmethod
    def _display_formula(rule: FormulaCard | Any) -> str:
        source = getattr(rule, "display_source", None) or ", ".join(getattr(rule, "source_selectors", []) or []) or "source"
        target = getattr(rule, "display_target", None) or ", ".join(getattr(rule, "target_selectors", []) or []) or "target"
        return f"Directed {source} -> Natal {target}"

    @staticmethod
    def _format_validation_report_table(report: dict[str, Any]) -> str:
        return (
            f"Карточка: {report.get('card_id')} | "
            f"Найдено: {len(report.get('found_by_engine', []))} | "
            f"Пропущено: {len(report.get('missed_by_engine', []))} | "
            f"Отклонено: {len(report.get('rejected_aspects', []))} | "
            f"Статус: {report.get('final_status_for_expert', 'needs_expert_review')}"
        )

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
