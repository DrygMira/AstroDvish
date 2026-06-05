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
        if card_id:
            card = self.loader.load_card(card_id)
            if str(card.event_type) != str(event_type):
                raise ValueError(
                    f"formula card {card_id} is configured for event_type={card.event_type}, not {event_type}"
                )
            cards = [card]
        else:
            cards = self.loader.load_by_event_type(event_type)
            cards = [card for card in cards if str(card.status).lower() != "draft"]
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
        candidate_birth_datetime_local = self._extract_candidate_datetime(context, "candidate_birth_datetime_local")
        candidate_birth_datetime_utc = self._extract_candidate_datetime(context, "candidate_birth_datetime_utc")
        timezone_used = self._extract_context_text(context, "timezone_used")
        timezone_offset_used = self._extract_context_text(context, "timezone_offset_used")
        candidate_consistency = self._build_candidate_consistency(context)

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
                candidate_birth_datetime_local=candidate_birth_datetime_local,
                candidate_birth_datetime_utc=candidate_birth_datetime_utc,
                timezone_used=timezone_used,
                timezone_offset_used=timezone_offset_used,
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
                - score_breakdown["ambiguity_penalty"]
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
            candidate_consistency=candidate_consistency,
        )

        directed_points_debug = self._build_directed_points_debug(rule_debug)
        natal_targets_debug = self._build_natal_targets_debug(rule_debug)
        card_summary = self._card_summary(card)

        return FormulaTestModeResult(
            card_id=card.card_id,
            event_type=card.event_type,
            status=card.status,
            card_version=card.card_version,
            card_hash=card.card_hash,
            source_file_path=card.source_file_path,
            formulas_count=card_summary["formulas_count"],
            priority_counts=card_summary["priority_counts"],
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
                "formulas_count": card_summary["formulas_count"],
                "priority_counts": card_summary["priority_counts"],
                "directed_points_debug": directed_points_debug,
                "natal_targets_debug": natal_targets_debug,
                "candidate_consistency": candidate_consistency,
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
                "timezone_used": timezone_used,
                "timezone_offset_used": timezone_offset_used,
                "non_scoring_methods": [item for item in methods_used if item != "directions"],
            },
        )

    @staticmethod
    def _card_summary(card: FormulaCard) -> dict[str, Any]:
        priority_counts = {
            "golden": 0,
            "supporting": 0,
            "context": 0,
            "ambiguity_risk": 0,
        }
        for rule in card.direction_rules:
            tier = str(getattr(rule, "priority_tier", "supporting") or "supporting")
            if tier not in priority_counts:
                priority_counts[tier] = 0
            priority_counts[tier] += 1
        return {
            "formulas_count": len(card.direction_rules),
            "priority_counts": priority_counts,
        }

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
    def _extract_candidate_datetime(context: dict[str, Any], key: str) -> str | None:
        raw = context.get(key)
        if raw is None:
            return None
        return str(raw)

    @staticmethod
    def _extract_context_text(context: dict[str, Any], key: str) -> str | None:
        raw = context.get(key)
        if raw is None or raw == "":
            return None
        return str(raw)

    @staticmethod
    def _build_candidate_consistency(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "selected_candidate_time": context.get("selected_candidate_time"),
            "chart_build_time": context.get("chart_build_time"),
            "natal_houses_time": context.get("natal_houses_time"),
            "rulers_resolved_time": context.get("rulers_resolved_time"),
            "house_elements_resolved_time": context.get("house_elements_resolved_time"),
            "directed_points_time": context.get("directed_points_time"),
            "candidate_birth_datetime_local": context.get("candidate_birth_datetime_local"),
            "candidate_birth_datetime_utc": context.get("candidate_birth_datetime_utc"),
            "timezone_used": context.get("timezone_used"),
            "timezone_offset_used": context.get("timezone_offset_used"),
            "timezone_source": context.get("timezone_source"),
            "timezone_name": context.get("timezone_name"),
            "utc_offset": context.get("utc_offset"),
            "coordinates_used": context.get("coordinates_used"),
            "birth_date_local": context.get("birth_date_local") or context.get("candidate_birth_date"),
            "birth_time_local": context.get("selected_candidate_time") or context.get("candidate_birth_datetime_local"),
            "rectification_stage": context.get("rectification_stage"),
            "payload_path": context.get("payload_path"),
        }

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
        best_matches_by_rule: dict[str, Any] = {}
        for item in scoring_formula_aspects:
            rule_id = str(getattr(item, "formula_rule_matched", ""))
            if not rule_id:
                continue
            current = best_matches_by_rule.get(rule_id)
            if current is None or float(getattr(item, "orb", 999.0)) < float(getattr(current, "orb", 999.0)):
                best_matches_by_rule[rule_id] = item
        unique_debug_rules = {
            str(getattr(item, "formula_rule_matched", ""))
            for item in debug_optional_formula_aspects
        }
        golden_formula_points = 0.0
        supporting_formula_points = 0.0
        context_formula_points = 0.0
        ambiguity_penalty = 0.0
        for item in best_matches_by_rule.values():
            weight = float(getattr(item, "rule_weight", 1.0) or 1.0)
            priority_tier = str(getattr(item, "priority_tier", "supporting") or "supporting")
            if priority_tier == "golden":
                golden_formula_points += weight * 4.0
            elif priority_tier == "supporting":
                supporting_formula_points += weight * 2.0
            elif priority_tier == "context":
                context_formula_points += weight * 0.5
            elif priority_tier == "ambiguity_risk":
                ambiguity_penalty += weight * 1.0
        return {
            "matched_core_points": len(matched_core) * 12.0,
            "matched_aspect_points": len(matched_aspects) * 8.0,
            "matched_strong_points": len(matched_strong) * 7.0,
            "matched_weak_points": len(matched_weak) * 3.0,
            "golden_formula_points": round(golden_formula_points, 4),
            "supporting_formula_points": round(supporting_formula_points, 4),
            "context_formula_points": round(context_formula_points, 4),
            "matched_formula_aspect_points": round(golden_formula_points + supporting_formula_points + context_formula_points, 4),
            "debug_optional_formula_aspect_points": 0.0,
            "debug_optional_formula_aspect_count": float(len(unique_debug_rules)),
            "ambiguity_penalty": round(ambiguity_penalty, 4),
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
        candidate_consistency: dict[str, Any],
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
        ambiguity_risks = [item for item in found if item.get("priority_tier") == "ambiguity_risk"]
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
            "ambiguity_risks": ambiguity_risks,
            "extra_or_suspicious_aspects": suspicious,
            "score_breakdown": score_breakdown,
            "rule_debug": rule_debug,
            "directed_points_debug": cls._build_directed_points_debug(rule_debug),
            "natal_targets_debug": cls._build_natal_targets_debug(rule_debug),
            "candidate_consistency": candidate_consistency,
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
                ambiguity_risks=ambiguity_risks,
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
        ambiguity_risks: list[dict[str, Any]],
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
        if ambiguity_risks:
            labels = [str(item.get("formula_rule_matched") or item.get("directed_point") or "ambiguity_rule") for item in ambiguity_risks]
            questions.append(f"Проверить ambiguity-risk связи: {', '.join(labels)}.")
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
                    "role": pair.get("source_role"),
                    "ruler_type": pair.get("source_ruler_type"),
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
                    "role": pair.get("target_role"),
                    "ruler_type": pair.get("target_ruler_type"),
                    "natal_longitude": pair.get("natal_coordinate"),
                }
        return list(points.values())

    @staticmethod
    def _display_formula(rule: FormulaCard | Any) -> str:
        if getattr(rule, "formula", None):
            return str(getattr(rule, "formula"))
        source = getattr(rule, "display_source", None) or ", ".join(getattr(rule, "source_selectors", []) or []) or "source"
        target = getattr(rule, "display_target", None) or ", ".join(getattr(rule, "target_selectors", []) or []) or "target"
        return f"Directed {source} -> Natal {target}"

    @staticmethod
    def _format_validation_report_table(report: dict[str, Any]) -> str:
        candidate_consistency = report.get("candidate_consistency") or {}
        lines = [
            f"Card: {report.get('card_id')} | Found: {len(report.get('found_by_engine', []))} | Missed: {len(report.get('missed_by_engine', []))} | Rejected: {len(report.get('rejected_aspects', []))} | Status: {report.get('final_status_for_expert', 'needs_expert_review')}",
            (
                "Candidate consistency | "
                f"selected_candidate_time={candidate_consistency.get('selected_candidate_time') or '-'} | "
                f"chart_build_time={candidate_consistency.get('chart_build_time') or '-'} | "
                f"natal_houses_time={candidate_consistency.get('natal_houses_time') or '-'} | "
                f"rulers_resolved_time={candidate_consistency.get('rulers_resolved_time') or '-'} | "
                f"house_elements_resolved_time={candidate_consistency.get('house_elements_resolved_time') or '-'} | "
                f"directed_points_time={candidate_consistency.get('directed_points_time') or '-'} | "
                f"timezone_used={candidate_consistency.get('timezone_used') or '-'} | "
                f"event_date_used={(report.get('rule_debug') or [{}])[0].get('event_date_used', '-') if report.get('rule_debug') else '-'} | "
                f"direction_arc={(report.get('rule_debug') or [{}])[0].get('direction_arc', '-') if report.get('rule_debug') else '-'}"
            ),
            "Formula | Rule | Priority | Formula role | Status | Directed source | Source type | Directed longitude | Natal target | Target type | Natal longitude | Aspect | Actual angle | Exact angle | Orb | Orb limit | Ruler type | Resolved source group | Resolved target group | Include reason | Exclude reason | Reject reason | closest_major_aspect_mismatch",
        ]
        missing_by_rule_id = {
            str(item.get("rule_id")): item
            for item in report.get("missed_by_engine", [])
            if isinstance(item, dict) and item.get("rule_id")
        }
        for rule in report.get("rule_debug", []) or []:
            matched_pairs = rule.get("matched_pairs") or []
            rejected_pairs = rule.get("rejected_pairs") or []
            checked_pairs = rule.get("checked_pairs") or []
            sample = matched_pairs[0] if matched_pairs else (rejected_pairs[0] if rejected_pairs else (checked_pairs[0] if checked_pairs else None))
            status = "matched" if matched_pairs else ("rejected" if rejected_pairs else "missed")
            reject_reason = "-"
            mismatch_payload = None
            if status == "rejected":
                reject_reason = str((sample or {}).get("reason") or missing_by_rule_id.get(str(rule.get("rule_id")), {}).get("reason") or "over_orb")
            elif status == "missed":
                reject_reason = str(missing_by_rule_id.get(str(rule.get("rule_id")), {}).get("reason") or "unresolved")
                mismatch_payload = missing_by_rule_id.get(str(rule.get("rule_id")), {}).get("details")
            if mismatch_payload is None:
                mismatch_payload = next(
                    (
                        item
                        for item in (rule.get("warnings") or [])
                        if isinstance(item, dict) and item.get("closest_major_aspect")
                    ),
                    None,
                )
            selector_decisions = list(rule.get("source_selector_decisions") or []) + list(rule.get("target_selector_decisions") or [])
            include_reason = ", ".join(
                sorted({str(item.get("selector")) for item in selector_decisions if item.get("include_reason")})
            ) or "-"
            exclude_reason = ", ".join(
                sorted(
                    {
                        f"{item.get('selector')}:{item.get('exclude_reason')}"
                        for item in selector_decisions
                        if item.get("exclude_reason")
                    }
                )
            ) or "-"
            ruler_resolution = list(rule.get("source_ruler_resolution") or []) + list(rule.get("target_ruler_resolution") or [])
            ruler_types = ", ".join(
                sorted({str(item.get("ruler_type")) for item in ruler_resolution if item.get("ruler_type")})
            ) or str((sample or {}).get("source_ruler_type") or (sample or {}).get("target_ruler_type") or "-")
            mismatch_text = "-"
            if mismatch_payload:
                mismatch_text = (
                    f"configured={','.join(mismatch_payload.get('configured_aspects', []))}; "
                    f"closest={mismatch_payload.get('closest_major_aspect')}; "
                    f"actual={mismatch_payload.get('actual_angle')}; "
                    f"exact={mismatch_payload.get('closest_major_exact_angle')}; "
                    f"orb_to_configured={(sample or {}).get('orb', '-')}; "
                    f"orb_to_closest={mismatch_payload.get('closest_major_orb')}"
                )
            lines.append(
                " | ".join(
                    [
                        str(rule.get("display_formula") or rule.get("title") or rule.get("rule_id") or "-"),
                        str(rule.get("rule_id") or "-"),
                        str(rule.get("priority") or rule.get("priority_tier") or "-"),
                        str(rule.get("role") or "-"),
                        status,
                        str((sample or {}).get("directed_point") or ", ".join(rule.get("resolved_sources") or []) or "-"),
                        str((sample or {}).get("source_type") or "-"),
                        str((sample or {}).get("directed_coordinate", "-")),
                        str((sample or {}).get("natal_target") or ", ".join(rule.get("resolved_targets") or []) or "-"),
                        str((sample or {}).get("target_type") or "-"),
                        str((sample or {}).get("natal_coordinate", "-")),
                        str((sample or {}).get("aspect_type", "-")),
                        str((sample or {}).get("actual_angle", "-")),
                        str((sample or {}).get("exact_angle", "-")),
                        str((sample or {}).get("orb", "-")),
                        str((sample or {}).get("orb_limit", "-")),
                        ruler_types,
                        str(rule.get("resolved_source_group") or rule.get("resolved_source_groups") or "-"),
                        str(rule.get("resolved_target_group") or rule.get("resolved_target_groups") or "-"),
                        include_reason,
                        exclude_reason,
                        reject_reason,
                        mismatch_text,
                    ]
                )
            )
        return "\n".join(lines)

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
