from __future__ import annotations

from datetime import datetime

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
        settings = payload.settings
        generation = self.candidate_generator.generate(
            birth_date_local=payload.birth_date_local,
            timezone_name=payload.timezone_name,
            asc_windows=payload.asc_windows,
            step_minutes=settings.candidate_step_minutes,
            max_candidates=settings.max_candidates,
        )
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
        top_total = -1.0
        top_candidate_id = ""

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
                best_method_results = {
                    "directions": method_results_for_candidate.get("directions", []),
                    "solars": method_results_for_candidate.get("solar", []),
                    "lunars": method_results_for_candidate.get("lunar", []),
                    "transits": method_results_for_candidate.get("transits", []),
                    "totems": method_results_for_candidate.get("totem", []),
                }

        candidate_scores.sort(key=lambda item: float(item.scores.get("total") or 0.0), reverse=True)
        best_candidates = candidate_scores[:3]
        best_candidate = best_candidates[0] if best_candidates else None
        confidence = self.confidence_service.summarize(best_candidate=best_candidate, events=payload.events)
        formula_refinement_results = self.formula_refinement_service.refine(payload)
        formula_refinement_results["coarse_candidate"] = self._build_coarse_candidate_summary(best_candidate)
        refined_chart = self._chart_from_refinement_candidate(formula_refinement_results)
        self._strip_refinement_internal_chart(formula_refinement_results)
        formula_test_mode_results = self._build_formula_test_mode_results(
            payload=payload,
            best_chart=refined_chart or best_chart,
            method_results=best_method_results,
        )

        if confidence.level in {"low", "medium"}:
            warnings.append("do_not_present_as_exact_birth_time")
        if len(payload.events) < 3:
            warnings.append("insufficient_events_for_strong_rectification")

        return RectificationProRunResponse(
            candidate_windows=candidate_scores,
            best_candidates=best_candidates,
            method_results=best_method_results,
            formula_test_mode_results=formula_test_mode_results,
            formula_refinement_results=formula_refinement_results,
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
                        "event": event.model_dump(mode="json"),
                        "pro_result": {"method_results": method_results},
                    },
                )
            except ValueError:
                continue
            results.append(result)
        return results

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
