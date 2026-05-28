from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.models.formula_card_models import FormulaTestModeResult
from app.models.rectification_pro_models import ProAscWindow, RectificationProRunRequest
from app.models.request_models import ChartRequest
from app.services.ephemeris_service import EphemerisService
from app.services.rectification_formula.formula_test_mode_service import FormulaTestModeService


class FormulaRefinementService:
    SUPPORTED_STEP_SECONDS = [300, 60, 30, 10]

    def __init__(
        self,
        *,
        ephemeris_service: EphemerisService,
        formula_test_mode_service: FormulaTestModeService,
    ) -> None:
        self.ephemeris_service = ephemeris_service
        self.formula_test_mode_service = formula_test_mode_service

    def refine(self, payload: RectificationProRunRequest, *, card_id: str | None = None) -> dict[str, Any]:
        if not payload.settings.formula_refinement_enabled:
            return {
                "enabled": False,
                "step_seconds": payload.settings.formula_refinement_step_seconds,
                "supported_step_seconds": self.SUPPORTED_STEP_SECONDS,
                "scanned_candidates_count": 0,
                "top_candidates": [],
                "best_candidate": None,
                "coarse_candidate": None,
                "working_time_ranges": [],
                "working_time_range": None,
                "reference_time": {
                    "provided": payload.settings.formula_reference_time_local,
                    "inside_working_time_range": False,
                    "evaluation": None,
                },
                "legacy_mode": True,
            }

        candidates: list[dict[str, Any]] = []
        step_seconds = payload.settings.formula_refinement_step_seconds
        for window in payload.asc_windows:
            for candidate_time_local, candidate_time_utc in self._iter_window_candidates(
                birth_date_local=payload.birth_date_local,
                timezone_name=payload.timezone_name,
                window=window,
                step_seconds=step_seconds,
            ):
                chart = self.ephemeris_service.calculate_chart(
                    ChartRequest(
                        datetime_utc=candidate_time_utc,
                        latitude=payload.latitude,
                        longitude=payload.longitude,
                        house_system=payload.house_system,
                        zodiac_mode=payload.zodiac_mode,
                        sidereal_mode=payload.sidereal_mode,
                    )
                )
                event_results = self._evaluate_events(payload=payload, chart=chart, card_id=card_id)
                candidate_result = self._score_candidate(
                    candidate_time_local=candidate_time_local,
                    candidate_time_utc=candidate_time_utc,
                    source_window=window,
                    event_results=event_results,
                    chart_response=chart.model_dump(mode="json"),
                )
                candidates.append(candidate_result)

        candidates.sort(
            key=lambda item: (
                -int(item["golden_matched_count"]),
                float(item["golden_orb_sum"]),
                -int(item["supporting_matched_count"]),
                -float(item["supporting_bonus"]),
                -float(item["score"]),
                item["candidate_time_local"],
            ),
        )
        top_candidates = candidates[:5]
        self._annotate_selection_reason(top_candidates)
        working_time_ranges = self._build_working_time_ranges(candidates, step_seconds)
        best_candidate = top_candidates[0] if top_candidates else None
        working_time_range = self._select_primary_working_time_range(
            working_time_ranges=working_time_ranges,
            best_candidate=best_candidate,
        )
        reference_time = self._build_reference_time(payload=payload, card_id=card_id)
        if working_time_ranges and reference_time.get("provided"):
            provided = str(reference_time["provided"])
            reference_time["inside_working_time_range"] = any(
                item["start_local"] <= provided <= item["end_local"] for item in working_time_ranges
            )
        card_meta = self._extract_card_meta(best_candidate)
        return {
            "enabled": True,
            "step_seconds": step_seconds,
            "supported_step_seconds": self.SUPPORTED_STEP_SECONDS,
            "direction_method": self.formula_test_mode_service.default_direction_method,
            "card_id": card_meta.get("card_id"),
            "card_version": card_meta.get("card_version"),
            "formulas_count": card_meta.get("formulas_count"),
            "priority_counts": card_meta.get("priority_counts", {}),
            "scanned_candidates_count": len(candidates),
            "top_candidates": top_candidates,
            "best_candidate": best_candidate,
            "coarse_candidate": None,
            "working_time_ranges": working_time_ranges,
            "working_time_range": working_time_range,
            "reference_time": reference_time,
            "legacy_mode": False,
        }

    def _evaluate_events(
        self,
        *,
        payload: RectificationProRunRequest,
        chart,
        card_id: str | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for event in payload.events:
            normalized_event_type = self._normalize_formula_event_type(str(event.event_type.value))
            if normalized_event_type is None:
                continue
            try:
                result = self.formula_test_mode_service.evaluate(
                    event_type=normalized_event_type,
                    context={
                        "chart_response": chart.model_dump(mode="json"),
                        "candidate_birth_date": payload.birth_date_local.isoformat(),
                        "event": event.model_dump(mode="json"),
                        "direction_method": "symbolic_1deg_per_year",
                    },
                    card_id=card_id,
                )
            except ValueError:
                continue
            results.append(result)
        return results

    @staticmethod
    def _score_candidate(
        *,
        candidate_time_local: str,
        candidate_time_utc: str,
        source_window: ProAscWindow,
        event_results: list[dict[str, Any]],
        chart_response: dict[str, Any],
    ) -> dict[str, Any]:
        matched_count = 0
        rejected_count = 0
        missing_count = 0
        matched_formula_score = 0.0
        orb_strength_score = 0.0
        participant_bonus_score = 0.0
        best_formulas: list[str] = []
        golden_matches_by_rule: dict[str, dict[str, Any]] = {}
        supporting_matches_by_rule: dict[str, dict[str, Any]] = {}
        context_matches_by_rule: dict[str, dict[str, Any]] = {}
        ambiguity_matches_by_rule: dict[str, dict[str, Any]] = {}
        event_contribution_audit: list[dict[str, Any]] = []
        rejected_reason_counts: dict[str, int] = {}

        for result in event_results:
            matched_formula_score += float(result.get("score") or 0.0)
            matched = result.get("matched_formula_aspects") or []
            rejected = result.get("rejected_aspects") or []
            missing = result.get("missing_formula_links") or []
            matched_count += len(matched)
            rejected_count += len(rejected)
            missing_count += len(missing)
            for item in matched:
                orb = float(item.get("orb") or 0.0)
                orb_strength_value = FormulaRefinementService._orb_strength_value(orb)
                participant_bonus_value = FormulaRefinementService._participant_bonus(item)
                priority_tier = str(item.get("priority_tier") or "supporting")
                rule_id = str(item.get("formula_rule_matched") or "")
                match_payload = {
                    "rule_id": rule_id,
                    "orb": orb,
                    "orb_strength_value": orb_strength_value,
                    "participant_bonus_value": participant_bonus_value,
                    "weight": float(item.get("rule_weight") or 0.0),
                    "shape": FormulaRefinementService._match_shape(item),
                }
                if priority_tier == "golden":
                    existing = golden_matches_by_rule.get(rule_id)
                    if existing is None or orb < float(existing["orb"]):
                        golden_matches_by_rule[rule_id] = match_payload
                elif priority_tier == "supporting":
                    existing = supporting_matches_by_rule.get(rule_id)
                    if existing is None or orb < float(existing["orb"]):
                        supporting_matches_by_rule[rule_id] = match_payload
                elif priority_tier == "context":
                    existing = context_matches_by_rule.get(rule_id)
                    if existing is None or orb < float(existing["orb"]):
                        context_matches_by_rule[rule_id] = match_payload
                elif priority_tier == "ambiguity_risk":
                    existing = ambiguity_matches_by_rule.get(rule_id)
                    if existing is None or orb < float(existing["orb"]):
                        ambiguity_matches_by_rule[rule_id] = match_payload
                orb_closeness_value = max(0.0, 1.0 - (orb / max(float(item.get("orb_limit") or 0.0), 0.0001)))
                orb_strength_score += orb_closeness_value
                participant_bonus_score += participant_bonus_value
                best_formulas.append(
                    f"{item.get('formula_rule_matched')}:{item.get('directed_point')}->{item.get('natal_target')}:{item.get('aspect_type')}"
                )
            for item in rejected:
                reason = str(item.get("rejection_reason") or item.get("reason") or "unknown")
                rejected_reason_counts[reason] = rejected_reason_counts.get(reason, 0) + 1

            event_golden_rules = {
                str(item.get("formula_rule_matched") or "")
                for item in matched
                if str(item.get("priority_tier") or "") == "golden"
            }
            event_supporting_rules = {
                str(item.get("formula_rule_matched") or "")
                for item in matched
                if str(item.get("priority_tier") or "supporting") == "supporting"
            }
            event_context_rules = {
                str(item.get("formula_rule_matched") or "")
                for item in matched
                if str(item.get("priority_tier") or "") == "context"
            }
            event_ambiguity_rules = {
                str(item.get("formula_rule_matched") or "")
                for item in matched
                if str(item.get("priority_tier") or "") == "ambiguity_risk"
            }

            event_contribution_audit.append(
                {
                    "event_id": result.get("source_event_id"),
                    "event_type": result.get("source_event_type") or result.get("event_type"),
                    "event_title": result.get("source_event_title"),
                    "event_date": result.get("source_event_date"),
                    "card_id": result.get("card_id"),
                    "score": float(result.get("score") or 0.0),
                    "matched_count": len(matched),
                    "rejected_count": len(rejected),
                    "missed_count": len(missing),
                    "golden_matched_count": len(event_golden_rules),
                    "supporting_matched_count": len(event_supporting_rules),
                    "context_matched_count": len(event_context_rules),
                    "ambiguity_risk_count": len(event_ambiguity_rules),
                }
            )

        total_event_score = sum(float(item["score"]) for item in event_contribution_audit) or 0.0
        for item in event_contribution_audit:
            contribution = 0.0 if total_event_score <= 0 else round((float(item["score"]) / total_event_score) * 100.0, 2)
            item["contribution_to_final_candidate"] = contribution

        golden_matched_count = len(golden_matches_by_rule)
        golden_orb_sum = round(sum(float(item["orb"]) for item in golden_matches_by_rule.values()), 4)
        golden_formula_score = round(sum(float(item["weight"]) * 10.0 for item in golden_matches_by_rule.values()), 4)
        golden_orb_quality_score = round(sum(float(item["orb_strength_value"]) for item in golden_matches_by_rule.values()), 4)
        supporting_matched_count = len(supporting_matches_by_rule)
        context_matched_count = len(context_matches_by_rule)
        supporting_formula_score = round(sum(float(item["weight"]) * 3.0 for item in supporting_matches_by_rule.values()), 4)
        context_formula_score = round(sum(float(item["weight"]) * 0.5 for item in context_matches_by_rule.values()), 4)
        supporting_bonus = round(
            sum(float(item["participant_bonus_value"]) for item in supporting_matches_by_rule.values())
            + (sum(float(item["orb_strength_value"]) for item in supporting_matches_by_rule.values()) * 0.5)
            + (sum(float(item["orb_strength_value"]) for item in context_matches_by_rule.values()) * 0.1),
            4,
        )
        ambiguity_penalty = round(sum(float(item["weight"]) * 1.5 for item in ambiguity_matches_by_rule.values()), 4)
        event_confirmation_score = round(
            sum(
                float(item["weight"]) * (float(item["orb_strength_value"]) + 1.0)
                for item in [*golden_matches_by_rule.values(), *supporting_matches_by_rule.values(), *context_matches_by_rule.values()]
                if str(item.get("shape") or "") == "planet_to_planet"
            ),
            4,
        )
        time_refinement_score = round(
            sum(
                float(item["weight"]) * (float(item["orb_strength_value"]) + 1.0)
                for item in [*golden_matches_by_rule.values(), *supporting_matches_by_rule.values(), *context_matches_by_rule.values()]
                if str(item.get("shape") or "") == "cusp_or_angle"
            ),
            4,
        )
        rejected_penalty = rejected_count * 0.5
        missing_penalty = missing_count * 0.25
        final_score = round(
            golden_formula_score
            + golden_orb_quality_score
            + supporting_formula_score
            + context_formula_score
            + supporting_bonus
            - ambiguity_penalty
            - rejected_penalty
            - missing_penalty,
            4,
        )
        return {
            "candidate_time_local": candidate_time_local,
            "candidate_time_utc": candidate_time_utc,
            "score": final_score,
            "base_formula_score": round(matched_formula_score, 4),
            "orb_closeness_score": round(orb_strength_score, 4),
            "matched_count": matched_count,
            "rejected_count": rejected_count,
            "missing_count": missing_count,
            "golden_matched_count": golden_matched_count,
            "golden_orb_sum": golden_orb_sum,
            "supporting_matched_count": supporting_matched_count,
            "context_matched_count": context_matched_count,
            "supporting_bonus": supporting_bonus,
            "event_confirmation_score": event_confirmation_score,
            "time_refinement_score": time_refinement_score,
            "score_breakdown": {
                "matched_formula_score": round(matched_formula_score, 4),
                "orb_strength_score": round(orb_strength_score, 4),
                "participant_bonus_score": round(participant_bonus_score, 4),
                "golden_formula_score": golden_formula_score,
                "golden_orb_quality_score": golden_orb_quality_score,
                "supporting_formula_score": supporting_formula_score,
                "context_formula_score": context_formula_score,
                "supporting_bonus": supporting_bonus,
                "ambiguity_penalty": ambiguity_penalty,
                "event_confirmation_score": event_confirmation_score,
                "time_refinement_score": time_refinement_score,
                "rejected_penalty": round(rejected_penalty, 4),
                "missing_penalty": round(missing_penalty, 4),
            },
            "source_asc_interval": source_window.model_dump(mode="json"),
            "formula_test_mode_results": event_results,
            "best_formulas": best_formulas[:10],
            "top_rejected_reasons": [
                {"reason": reason, "count": count}
                for reason, count in sorted(rejected_reason_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
            ],
            "event_contribution_audit": event_contribution_audit,
            "selection_reason": "",
            "chart_response": chart_response,
        }

    @staticmethod
    def _iter_window_candidates(
        *,
        birth_date_local: date,
        timezone_name: str,
        window: ProAscWindow,
        step_seconds: int,
    ) -> list[tuple[str, str]]:
        tz = ZoneInfo(timezone_name)
        day_start = datetime.combine(birth_date_local, time(0, 0, 0))
        day_end = day_start + timedelta(days=1)
        start_local = max(datetime.fromisoformat(window.start_local), day_start)
        end_local = min(datetime.fromisoformat(window.end_local), day_end)
        if end_local < start_local:
            return []

        step = timedelta(seconds=step_seconds)
        probe = start_local
        out: list[tuple[str, str]] = []
        while probe <= end_local:
            utc_dt = probe.replace(tzinfo=tz).astimezone(timezone.utc)
            out.append(
                (
                    probe.isoformat(timespec="seconds"),
                    utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
                )
            )
            probe += step
        return out

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

    @staticmethod
    def _orb_strength_value(orb: float) -> float:
        if orb <= 0.1667:
            return 4.0
        if orb <= 0.5:
            return 3.0
        if orb <= 1.0:
            return 2.0
        if orb <= 1.5:
            return 1.0
        return 0.0

    @staticmethod
    def _participant_bonus(item: dict[str, Any]) -> float:
        directed = str(item.get("directed_point") or "")
        natal = str(item.get("natal_target") or "")
        bonus = 0.0
        for point in (directed, natal):
            lowered = point.lower()
            if "cusp_" in lowered:
                bonus += 0.4
            if "ruler_" in lowered:
                bonus += 0.35
            if "house_element_" in lowered:
                bonus += 0.3
            if lowered in {"asc", "mc", "ic", "desc"}:
                bonus += 0.45
        return bonus

    @staticmethod
    def _match_shape(item: dict[str, Any]) -> str:
        directed = str(item.get("directed_point") or "").lower()
        natal = str(item.get("natal_target") or "").lower()
        angle_tokens = {"asc", "mc", "ic", "desc"}
        if (
            ":" not in directed
            and ":" not in natal
            and not directed.startswith("cusp_")
            and not natal.startswith("cusp_")
            and directed not in angle_tokens
            and natal not in angle_tokens
        ):
            return "planet_to_planet"
        if (
            directed.startswith("cusp_")
            or natal.startswith("cusp_")
            or directed in angle_tokens
            or natal in angle_tokens
        ):
            return "cusp_or_angle"
        return "mixed_symbolic"

    def _build_reference_time(
        self,
        *,
        payload: RectificationProRunRequest,
        card_id: str | None = None,
    ) -> dict[str, Any]:
        provided = payload.settings.formula_reference_time_local
        if not provided:
            return {"provided": None, "inside_working_time_range": False, "evaluation": None}

        tz = ZoneInfo(payload.timezone_name)
        local_dt = datetime.fromisoformat(provided)
        utc_dt = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)
        chart = self.ephemeris_service.calculate_chart(
            ChartRequest(
                datetime_utc=utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
                latitude=payload.latitude,
                longitude=payload.longitude,
                house_system=payload.house_system,
                zodiac_mode=payload.zodiac_mode,
                sidereal_mode=payload.sidereal_mode,
            )
        )
        event_results = self._evaluate_events(payload=payload, chart=chart, card_id=card_id)
        source_window = payload.asc_windows[0] if payload.asc_windows else ProAscWindow(
            start_local=provided,
            end_local=provided,
            sign_name_en="unknown",
            sign_name_ru=None,
        )
        evaluation = self._score_candidate(
            candidate_time_local=provided,
            candidate_time_utc=utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            source_window=source_window,
            event_results=event_results,
            chart_response=chart.model_dump(mode="json"),
        )
        evaluation.pop("chart_response", None)
        return {"provided": provided, "inside_working_time_range": False, "evaluation": evaluation}

    @staticmethod
    def _extract_card_meta(candidate: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            return {}
        formula_results = candidate.get("formula_test_mode_results")
        if not isinstance(formula_results, list) or not formula_results:
            return {}
        first = formula_results[0] if isinstance(formula_results[0], dict) else {}
        return {
            "card_id": first.get("card_id"),
            "card_version": first.get("card_version"),
            "formulas_count": first.get("formulas_count"),
            "priority_counts": first.get("priority_counts") or {},
        }

    @staticmethod
    def _build_working_time_ranges(candidates: list[dict[str, Any]], step_seconds: int) -> list[dict[str, Any]]:
        if not candidates:
            return []
        max_golden = max(int(item.get("golden_matched_count", 0)) for item in candidates)
        eligible = [item for item in candidates if int(item.get("golden_matched_count", 0)) == max_golden]
        if not eligible:
            return []
        eligible.sort(key=lambda item: item["candidate_time_local"])
        ranges: list[list[dict[str, Any]]] = []
        current_range: list[dict[str, Any]] = [eligible[0]]
        expected_gap = timedelta(seconds=step_seconds)
        for candidate in eligible[1:]:
            previous = current_range[-1]
            previous_dt = datetime.fromisoformat(previous["candidate_time_local"])
            current_dt = datetime.fromisoformat(candidate["candidate_time_local"])
            if current_dt - previous_dt == expected_gap:
                current_range.append(candidate)
                continue
            ranges.append(current_range)
            current_range = [candidate]
        ranges.append(current_range)
        return [
            FormulaRefinementService._build_single_working_time_range(chunk, max_golden)
            for chunk in ranges
        ]

    @staticmethod
    def _build_single_working_time_range(
        candidates: list[dict[str, Any]],
        golden_matched_count: int,
    ) -> dict[str, Any]:
        best_candidate = min(
            candidates,
            key=lambda item: (
                float(item["golden_orb_sum"]),
                -int(item["supporting_matched_count"]),
                -float(item["supporting_bonus"]),
                -float(item["score"]),
                item["candidate_time_local"],
            ),
        )
        return {
            "start_local": candidates[0]["candidate_time_local"],
            "end_local": candidates[-1]["candidate_time_local"],
            "candidate_count": len(candidates),
            "criterion": f"golden_matched_count={golden_matched_count}",
            "best_candidate": best_candidate["candidate_time_local"],
            "golden_matched_count": int(best_candidate.get("golden_matched_count", 0)),
            "score": float(best_candidate.get("score", 0.0)),
            "selection_reason": str(best_candidate.get("selection_reason") or "")
            or (
                f"Best in range by golden_orb_sum={best_candidate.get('golden_orb_sum', 'n/a')} "
                f"with golden_matched_count={best_candidate.get('golden_matched_count', 0)}."
            ),
        }

    @staticmethod
    def _select_primary_working_time_range(
        *,
        working_time_ranges: list[dict[str, Any]],
        best_candidate: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not working_time_ranges:
            return None
        if not best_candidate:
            return working_time_ranges[0]
        candidate_time = str(best_candidate.get("candidate_time_local") or "")
        for item in working_time_ranges:
            if item["start_local"] <= candidate_time <= item["end_local"]:
                return item
        return working_time_ranges[0]

    @staticmethod
    def _annotate_selection_reason(top_candidates: list[dict[str, Any]]) -> None:
        if not top_candidates:
            return
        leader = top_candidates[0]
        runner_up = top_candidates[1] if len(top_candidates) > 1 else None
        if runner_up is None:
            leader["selection_reason"] = (
                f"Won by golden_matched_count={leader.get('golden_matched_count', 0)} and "
                f"golden_orb_sum={leader.get('golden_orb_sum', 'n/a')}."
            )
            return

        if int(leader.get("golden_matched_count", 0)) != int(runner_up.get("golden_matched_count", 0)):
            leader["selection_reason"] = (
                f"Won by golden_matched_count: {leader.get('golden_matched_count')} vs {runner_up.get('golden_matched_count')}."
            )
            return
        if float(leader.get("golden_orb_sum", 999.0)) != float(runner_up.get("golden_orb_sum", 999.0)):
            leader["selection_reason"] = (
                f"Won by golden_orb_sum: {leader.get('golden_orb_sum')} vs {runner_up.get('golden_orb_sum')} "
                f"with equal golden_matched_count={leader.get('golden_matched_count')}."
            )
            return
        if int(leader.get("supporting_matched_count", 0)) != int(runner_up.get("supporting_matched_count", 0)):
            leader["selection_reason"] = (
                f"Won by supporting_matched_count after golden tie: "
                f"{leader.get('supporting_matched_count')} vs {runner_up.get('supporting_matched_count')}."
            )
            return
        leader["selection_reason"] = (
            f"Won by supporting_bonus after golden tie: "
            f"{leader.get('supporting_bonus')} vs {runner_up.get('supporting_bonus')}."
        )
