from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any

from app.models.rectification_pro_models import (
    CandidateScore,
    MethodMatch,
    RectificationProRunRequest,
    RectificationProRunResponse,
)
from app.models.request_models import ChartRequest
from app.services.ephemeris_service import EphemerisService
from app.services.rectification_formula.formula_test_mode_service import FormulaTestModeService
from app.services.rectification_pro.candidate_generator import CandidateGenerator
from app.services.rectification_pro.confidence_service import ConfidenceService
from app.services.rectification_pro.directions_service import DirectionsService
from app.services.rectification_pro.formula_refinement_service import FormulaRefinementService
from app.services.rectification_pro.lunar_service import LunarService
from app.services.rectification_pro.scoring_service import ScoringService
from app.services.rectification_pro.solar_service import SolarService
from app.services.rectification_pro.timezone_context import resolve_pro_timezone
from app.services.rectification_pro.totem_service import TotemService
from app.services.rectification_pro.transit_service import TransitService


class RectificationProService:
    def __init__(self, ephemeris_service: EphemerisService) -> None:
        self.ephemeris_service = ephemeris_service
        self.candidate_generator = CandidateGenerator()
        self.formula_test_mode_service = FormulaTestModeService(ephemeris_service=ephemeris_service)
        self.directions_service = DirectionsService()
        self.formula_refinement_service = FormulaRefinementService(
            ephemeris_service=ephemeris_service,
            formula_test_mode_service=self.formula_test_mode_service,
        )
        self.solar_service = SolarService()
        self.lunar_service = LunarService()
        self.transit_service = TransitService()
        self.totem_service = TotemService()
        self.scoring_service = ScoringService()
        self.confidence_service = ConfidenceService()

    def run(self, payload: RectificationProRunRequest) -> RectificationProRunResponse:
        started_at = perf_counter()
        stage_timings: dict[str, float] = {}
        settings = payload.settings
        selected_formula_card_id = settings.formula_card_id or None
        timezone_info, timezone_used, timezone_offset_used = resolve_pro_timezone(payload)
        generation_started_at = perf_counter()
        generation = self.candidate_generator.generate(
            birth_date_local=payload.birth_date_local,
            timezone_info=timezone_info,
            asc_windows=payload.asc_windows,
            step_minutes=settings.candidate_step_minutes,
            max_candidates=settings.max_candidates,
        )
        stage_timings["candidate_generation_ms"] = round((perf_counter() - generation_started_at) * 1000, 2)
        warnings = list(generation.warnings)
        limitations = [
            "MVP: directions/solar/transits are lightweight scoring proxies, not full master-level event interpretation.",
            "Lunar module is placeholder and intentionally low-weight.",
            "Totem database is not connected; only technical degree index is returned.",
            "Result is probabilistic time windows, not guaranteed exact birth time.",
        ]

        if not generation.candidate_times:
            warnings.append("no_candidates_generated")
            confidence = self.confidence_service.summarize(best_candidate=None, events=payload.events)
            return RectificationProRunResponse(
                candidate_windows=[],
                best_candidates=[],
                method_results={"directions": [], "solars": [], "lunars": [], "transits": [], "totems": []},
                confidence=confidence,
                warnings=warnings,
                limitations=limitations,
            )

        candidate_scores: list[CandidateScore] = []
        best_method_results: dict[str, list[MethodMatch]] = {
            "directions": [],
            "solars": [],
            "lunars": [],
            "transits": [],
            "totems": [],
        }
        best_chart = None
        best_generation_candidate = None
        top_total = -1.0
        top_candidate_id = ""

        coarse_scoring_started_at = perf_counter()
        for candidate in generation.candidate_times:
            chart = self._chart_for_candidate(candidate.datetime_utc, payload)
            method_results_for_candidate: dict[str, list[MethodMatch]] = {}

            if settings.include_directions:
                method_results_for_candidate["directions"] = self.directions_service.evaluate_candidate(
                    candidate_chart=chart,
                    candidate_birth_date=payload.birth_date_local,
                    events=payload.events,
                    directions_orbs=settings.directions_orbs,
                )
            if settings.include_solars:
                method_results_for_candidate["solar"] = self.solar_service.evaluate_candidate(
                    candidate_chart=chart,
                    events=payload.events,
                )
            if settings.include_lunars:
                method_results_for_candidate["lunar"] = self.lunar_service.evaluate_candidate(
                    candidate_chart=chart,
                    events=payload.events,
                    include_lunars=True,
                )
            if settings.include_transits:
                method_results_for_candidate["transits"] = self.transit_service.evaluate_candidate(
                    candidate_chart=chart,
                    events=payload.events,
                )
            if settings.include_totems:
                method_results_for_candidate["totem"] = [
                    self.totem_service.as_method_match(event_id=event.event_id, candidate=candidate)
                    for event in payload.events
                ]

            score = self.scoring_service.score_candidate(
                candidate_id=candidate.candidate_id,
                candidate_time_local=candidate.datetime_local,
                source_asc_interval=candidate.source_asc_interval,
                clipped_by_birth_date=candidate.clipped_by_birth_date,
                method_results=method_results_for_candidate,
                events=payload.events,
                weights=settings.weights,
            )
            candidate_scores.append(score)

            total_score = float(score.scores.get("total") or 0.0)
            if total_score > top_total:
                top_total = total_score
                top_candidate_id = candidate.candidate_id
                best_chart = chart
                best_generation_candidate = candidate
                best_method_results = {
                    "directions": method_results_for_candidate.get("directions", []),
                    "solars": method_results_for_candidate.get("solar", []),
                    "lunars": method_results_for_candidate.get("lunar", []),
                    "transits": method_results_for_candidate.get("transits", []),
                    "totems": method_results_for_candidate.get("totem", []),
                }
        stage_timings["coarse_scoring_ms"] = round((perf_counter() - coarse_scoring_started_at) * 1000, 2)

        candidate_scores.sort(key=lambda item: float(item.scores.get("total") or 0.0), reverse=True)
        best_candidates = candidate_scores[:3]
        best_candidate = best_candidates[0] if best_candidates else None
        confidence = self.confidence_service.summarize(best_candidate=best_candidate, events=payload.events)
        refinement_started_at = perf_counter()
        formula_refinement_results = self.formula_refinement_service.refine(
            payload,
            card_id=selected_formula_card_id,
        )
        stage_timings["formula_refinement_ms"] = round((perf_counter() - refinement_started_at) * 1000, 2)
        formula_refinement_results["coarse_candidate"] = self._build_coarse_candidate_summary(best_candidate)
        refined_chart = self._chart_from_refinement_candidate(formula_refinement_results)
        self._strip_refinement_internal_chart(formula_refinement_results)
        formula_test_mode_started_at = perf_counter()
        formula_test_mode_results = self._build_formula_test_mode_results(
            payload=payload,
            best_chart=refined_chart or best_chart,
            method_results=best_method_results,
            card_id=selected_formula_card_id,
            candidate_time_local=(
                (formula_refinement_results.get("best_candidate") or {}).get("candidate_time_local")
                or (best_generation_candidate.datetime_local if best_generation_candidate else None)
            ),
            candidate_time_utc=(
                (formula_refinement_results.get("best_candidate") or {}).get("candidate_time_utc")
                or (best_generation_candidate.datetime_utc if best_generation_candidate else None)
            ),
            timezone_used=timezone_used,
            timezone_offset_used=timezone_offset_used,
        )
        stage_timings["formula_test_mode_ms"] = round((perf_counter() - formula_test_mode_started_at) * 1000, 2)
        comparison_started_at = perf_counter()
        formula_card_comparison = self._build_formula_card_comparison(
            payload=payload,
            method_results=best_method_results,
        )
        stage_timings["formula_card_comparison_ms"] = round((perf_counter() - comparison_started_at) * 1000, 2)

        if confidence.level in {"low", "medium"}:
            warnings.append("do_not_present_as_exact_birth_time")
        if len(payload.events) < 3:
            warnings.append("insufficient_events_for_strong_rectification")

        formulas_count = formula_refinement_results.get("formulas_count")
        if formulas_count is None and formula_test_mode_results:
            formulas_count = len(
                (formula_test_mode_results[0].expected_by_card or {}).get("direction_rules", [])
            )
        total_runtime_ms = round((perf_counter() - started_at) * 1000, 2)
        slowest_stage = None
        if stage_timings:
            slowest_stage = max(stage_timings.items(), key=lambda item: float(item[1]))[0]
        performance_debug = {
            "card_id": formula_refinement_results.get("card_id") or selected_formula_card_id,
            "formula_count": formulas_count,
            "event_count": len(payload.events),
            "candidate_count": len(generation.candidate_times),
            "total_runtime_ms": total_runtime_ms,
            "slowest_stage": slowest_stage,
            "stage_timings_ms": stage_timings,
        }

        return RectificationProRunResponse(
            candidate_windows=candidate_scores,
            best_candidates=best_candidates,
            method_results=best_method_results,
            formula_test_mode_results=formula_test_mode_results,
            formula_refinement_results=formula_refinement_results,
            formula_card_comparison=formula_card_comparison,
            performance_debug=performance_debug,
            confidence=confidence,
            warnings=sorted(set(warnings)),
            limitations=limitations,
        )

    def _chart_for_candidate(self, datetime_utc: str, payload: RectificationProRunRequest):
        request = ChartRequest(
            datetime_utc=datetime_utc,
            latitude=payload.latitude,
            longitude=payload.longitude,
            house_system=payload.house_system,
            zodiac_mode=payload.zodiac_mode,
            sidereal_mode=payload.sidereal_mode,
        )
        return self.ephemeris_service.calculate_chart(request)

    def _build_formula_test_mode_results(
        self,
        *,
        payload: RectificationProRunRequest,
        best_chart,
        method_results: dict[str, list[MethodMatch]],
        card_id: str | None = None,
        candidate_time_local: str | None = None,
        candidate_time_utc: str | None = None,
        timezone_used: str | None = None,
        timezone_offset_used: str | None = None,
    ) -> list:
        if best_chart is None:
            return []
        results = []
        for event in payload.events:
            normalized_event_type = self._normalize_formula_event_type(str(event.event_type.value))
            if normalized_event_type is None:
                continue
            try:
                result = self.formula_test_mode_service.evaluate(
                    event_type=normalized_event_type,
                    context={
                        "chart_response": best_chart.model_dump(mode="json"),
                        "candidate_birth_date": payload.birth_date_local.isoformat(),
                        "candidate_birth_datetime_local": candidate_time_local,
                        "candidate_birth_datetime_utc": candidate_time_utc,
                        "selected_candidate_time": candidate_time_local,
                        "chart_build_time": candidate_time_local,
                        "natal_houses_time": candidate_time_local,
                        "rulers_resolved_time": candidate_time_local,
                        "house_elements_resolved_time": candidate_time_local,
                        "directed_points_time": candidate_time_local,
                        "timezone_used": timezone_used or payload.timezone_name,
                        "timezone_offset_used": timezone_offset_used,
                        "event": event.model_dump(mode="json"),
                        "pro_result": {"method_results": method_results},
                    },
                    card_id=card_id,
                )
            except ValueError:
                continue
            results.append(result)
        return results

    def _build_formula_card_comparison(
        self,
        *,
        payload: RectificationProRunRequest,
        method_results: dict[str, list[MethodMatch]],
    ) -> dict[str, Any]:
        requested = self._normalize_compare_card_ids(payload.settings.compare_formula_card_ids)
        if not requested:
            return {}

        items: list[dict[str, Any]] = []
        for card_id in requested:
            refinement = self.formula_refinement_service.refine(payload, card_id=card_id)
            refinement["coarse_candidate"] = self._build_coarse_candidate_summary(None)
            refined_chart = self._chart_from_refinement_candidate(refinement)
            self._strip_refinement_internal_chart(refinement)
            formula_results = self._build_formula_test_mode_results(
                payload=payload,
                best_chart=refined_chart,
                method_results=method_results,
                card_id=card_id,
                candidate_time_local=(refinement.get("best_candidate") or {}).get("candidate_time_local"),
                candidate_time_utc=(refinement.get("best_candidate") or {}).get("candidate_time_utc"),
                timezone_used=refinement.get("timezone_used") or payload.timezone_name,
                timezone_offset_used=refinement.get("timezone_offset_used"),
            )
            card_meta = self._extract_formula_card_meta(formula_results, refinement, card_id)
            items.append(
                {
                    **card_meta,
                    "formula_refinement_results": refinement,
                    "formula_test_mode_results": formula_results,
                }
            )

        if not items:
            return {}

        selected_card_id = payload.settings.formula_card_id or items[-1]["card_id"]
        baseline_card_id = items[0]["card_id"]
        differences = self._build_formula_card_differences(items)
        return {
            "enabled": True,
            "baseline_card_id": baseline_card_id,
            "selected_card_id": selected_card_id,
            "items": self._build_formula_card_public_items(items),
            "differences": differences,
            "summary": self._build_formula_card_comparison_summary(
                baseline_card_id=baseline_card_id,
                selected_card_id=selected_card_id,
                items=items,
                differences=differences,
            ),
        }

    @staticmethod
    def _normalize_compare_card_ids(card_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in card_ids:
            value = str(raw or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _extract_formula_card_meta(
        formula_results: list[dict[str, Any]],
        refinement: dict[str, Any],
        fallback_card_id: str,
    ) -> dict[str, Any]:
        first_result = formula_results[0] if formula_results else {}
        return {
            "card_id": first_result.get("card_id") or refinement.get("card_id") or fallback_card_id,
            "card_version": first_result.get("card_version") or refinement.get("card_version"),
            "formulas_count": first_result.get("formulas_count") or refinement.get("formulas_count"),
            "priority_counts": first_result.get("priority_counts") or refinement.get("priority_counts") or {},
            "validation_report": first_result.get("validation_report") or {},
            "matched_formula_aspects": first_result.get("matched_formula_aspects") or [],
            "rejected_aspects": first_result.get("rejected_aspects") or [],
            "missing_formula_links": first_result.get("missing_formula_links") or [],
        }

    @staticmethod
    def _build_formula_card_differences(items: list[dict[str, Any]]) -> dict[str, Any]:
        working_ranges_difference = []
        best_candidate_difference = {}
        event_contribution_audit_difference = {}
        rules_by_card: dict[str, dict[str, dict[str, Any]]] = {}
        for item in items:
            card_id = str(item.get("card_id") or "unknown")
            refinement = item.get("formula_refinement_results") or {}
            best_candidate = refinement.get("best_candidate") or {}
            working_ranges = refinement.get("working_time_ranges") or []
            validation_report = item.get("validation_report") or {}
            expected_rules = ((validation_report.get("expected_by_card") or {}).get("direction_rules") or [])
            rules_by_card[card_id] = {
                str(rule.get("id") or ""): {
                    "id": rule.get("id"),
                    "display_formula": rule.get("display_formula") or rule.get("formula") or rule.get("id"),
                    "priority": rule.get("priority"),
                    "aspect": rule.get("aspect"),
                    "role": rule.get("role"),
                    "inherited_from_v1": bool(rule.get("inherited_from_v1")),
                    "inherited_from_card_id": rule.get("inherited_from_card_id"),
                }
                for rule in expected_rules
                if str(rule.get("id") or "").strip()
            }
            working_ranges_difference.append(
                {
                    "card_id": card_id,
                    "ranges_count": len(working_ranges),
                    "primary_range": refinement.get("working_time_range"),
                }
            )
            best_candidate_difference[card_id] = {
                "candidate_time_local": best_candidate.get("candidate_time_local"),
                "score": best_candidate.get("score"),
                "golden_matched_count": best_candidate.get("golden_matched_count"),
                "golden_orb_sum": best_candidate.get("golden_orb_sum"),
            }
            event_contribution_audit_difference[card_id] = best_candidate.get("event_contribution_audit") or []
        baseline_card_id = str(items[0].get("card_id") or "unknown")
        selected_card_id = str(items[-1].get("card_id") or "unknown")
        baseline_rules = rules_by_card.get(baseline_card_id, {})
        selected_rules = rules_by_card.get(selected_card_id, {})
        shared_rule_ids = sorted(set(baseline_rules).intersection(selected_rules))
        v1_only_rule_ids = sorted(set(baseline_rules) - set(selected_rules))
        v2_added_rule_ids = sorted(set(selected_rules) - set(baseline_rules))
        shared_rules = [selected_rules.get(rule_id) or baseline_rules.get(rule_id) for rule_id in shared_rule_ids]
        v1_only_rules = [baseline_rules[rule_id] for rule_id in v1_only_rule_ids]
        v2_added_rules = [selected_rules[rule_id] for rule_id in v2_added_rule_ids]
        why_result_changed = (
            "v2 adds a larger child_birth rule pack, so candidate ranking is driven by more golden/supporting confirmations than v1."
            if v2_added_rules
            else "v1 and v2 use the same visible rule set; result changes come only from scoring differences."
        )
        return {
            "working_time_ranges_difference": working_ranges_difference,
            "best_candidate_difference": best_candidate_difference,
            "event_contribution_audit_difference": event_contribution_audit_difference,
            "shared_rules": shared_rules,
            "v1_only_rules": v1_only_rules,
            "v2_added_rules": v2_added_rules,
            "why_result_changed": why_result_changed,
        }

    @staticmethod
    def _build_formula_card_comparison_summary(
        *,
        baseline_card_id: str,
        selected_card_id: str,
        items: list[dict[str, Any]],
        differences: dict[str, Any],
    ) -> dict[str, Any]:
        summary_items: list[dict[str, Any]] = []
        for item in items:
            refinement = item.get("formula_refinement_results") or {}
            best_candidate = refinement.get("best_candidate") or {}
            working_range = refinement.get("working_time_range") or {}
            event_audit = best_candidate.get("event_contribution_audit") or []
            event_contribution_score = round(sum(float(audit.get("score") or 0.0) for audit in event_audit), 4)
            summary_items.append(
                {
                    "card_id": item.get("card_id"),
                    "formulas_count": item.get("formulas_count"),
                    "priority_counts": item.get("priority_counts") or {},
                    "working_range": working_range,
                    "best_candidate": best_candidate.get("candidate_time_local"),
                    "matched": best_candidate.get("matched_count"),
                    "rejected": best_candidate.get("rejected_count"),
                    "missed": best_candidate.get("missing_count"),
                    "golden_matched": best_candidate.get("golden_matched_count"),
                    "supporting_matched": best_candidate.get("supporting_matched_count"),
                    "context_matched": best_candidate.get("context_matched_count"),
                    "context_score": best_candidate.get("context_score"),
                    "event_contribution_score": event_contribution_score,
                    "top_rejected_reasons": best_candidate.get("top_rejected_reasons") or [],
                    "unresolved_source_summary": best_candidate.get("unresolved_source_summary") or [],
                }
            )
        return {
            "baseline_card_id": baseline_card_id,
            "selected_card_id": selected_card_id,
            "items": summary_items,
            "shared_rules": differences.get("shared_rules") or [],
            "v1_only_rules": differences.get("v1_only_rules") or [],
            "v2_added_rules": differences.get("v2_added_rules") or [],
            "why_result_changed": differences.get("why_result_changed"),
        }

    @staticmethod
    def _build_formula_card_public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        public_items: list[dict[str, Any]] = []
        for item in items:
            refinement = item.get("formula_refinement_results") or {}
            public_items.append(
                {
                    "card_id": item.get("card_id"),
                    "card_version": item.get("card_version"),
                    "formulas_count": item.get("formulas_count"),
                    "priority_counts": item.get("priority_counts") or {},
                    "working_time_range": refinement.get("working_time_range") or {},
                    "best_candidate": (refinement.get("best_candidate") or {}).get("candidate_time_local"),
                }
            )
        return public_items

    @staticmethod
    def _chart_from_refinement_candidate(formula_refinement_results: dict[str, object]):
        best_candidate = formula_refinement_results.get("best_candidate")
        if not isinstance(best_candidate, dict):
            return None
        chart_response = best_candidate.get("chart_response")
        if not isinstance(chart_response, dict):
            return None
        from app.models.response_models import ChartResponse

        return ChartResponse.model_validate(chart_response)

    @staticmethod
    def _strip_refinement_internal_chart(formula_refinement_results: dict[str, object]) -> None:
        top_candidates = formula_refinement_results.get("top_candidates")
        if isinstance(top_candidates, list):
            for item in top_candidates:
                if isinstance(item, dict):
                    item.pop("chart_response", None)
        best_candidate = formula_refinement_results.get("best_candidate")
        if isinstance(best_candidate, dict):
            best_candidate.pop("chart_response", None)

    @staticmethod
    def _build_coarse_candidate_summary(best_candidate: CandidateScore | None) -> dict[str, object] | None:
        if best_candidate is None:
            return None
        return {
            "candidate_id": best_candidate.candidate_id,
            "candidate_time_local": best_candidate.candidate_time_local,
            "candidate_window": best_candidate.candidate_window,
            "score": float(best_candidate.scores.get("total") or 0.0),
            "confidence_level": best_candidate.confidence_level,
            "matched_events_count": best_candidate.matched_events_count,
            "strong_events_matched_count": best_candidate.strong_events_matched_count,
            "source_asc_interval": best_candidate.source_asc_interval,
            "clipped_by_birth_date": best_candidate.clipped_by_birth_date,
        }

    @staticmethod
    def _normalize_formula_event_type(event_type: str) -> str | None:
        mapping = {
            "child_birth": "child_birth",
            "children_birth": "child_birth",
            "marriage_start": "marriage_union",
            "marriage_relationship": "relationship_start",
            "divorce_separation": "divorce_breakup",
            "death_father": "death_close_person",
            "death_mother": "death_close_person",
            "death_child": "death_close_person",
            "death_spouse": "death_close_person",
            "death_sibling": "death_close_person",
            "death_grandparent": "death_close_person",
            "death_close_person_other": "death_close_person",
            "death_of_close_person": "death_close_person",
        }
        return mapping.get(event_type)
