from __future__ import annotations

from collections import defaultdict
from statistics import mean

from app.models.event_models import DatePrecision, EventCard, Reversibility
from app.models.rectification_pro_models import CandidateScore, MethodMatch


class ScoringService:
    def score_candidate(
        self,
        *,
        candidate_id: str,
        candidate_time_local: str,
        source_asc_interval: dict[str, str] | None = None,
        clipped_by_birth_date: bool = False,
        method_results: dict[str, list[MethodMatch]],
        events: list[EventCard],
        weights: dict[str, float],
    ) -> CandidateScore:
        per_method_scores: dict[str, float | None] = {
            "directions": None,
            "solar": None,
            "transits": None,
            "lunar": None,
            "totem": None,
        }
        per_method_event_scores: dict[str, list[float]] = defaultdict(list)
        warnings: list[str] = []

        for method_name, results in method_results.items():
            if not results:
                continue
            scores = [float(item.event_score) for item in results]
            if scores:
                per_method_scores[method_name] = round(mean(scores), 2)
                per_method_event_scores[method_name].extend(scores)
            for item in results:
                warnings.extend(item.warnings)

        available_methods = [name for name, score in per_method_scores.items() if score is not None]
        total = self._weighted_total(per_method_scores=per_method_scores, weights=weights, available_methods=available_methods)
        event_map = {event.event_id: event for event in events}
        matched_events = 0
        strong_matched = 0
        for event_id, event in event_map.items():
            event_support = 0.0
            supporting_methods = 0
            for method_name in available_methods:
                results = method_results.get(method_name, [])
                hit = next((item for item in results if item.event_id == event_id), None)
                if hit is None or hit.event_score <= 0:
                    continue
                event_support += hit.event_score
                supporting_methods += 1
            if supporting_methods > 0 and event_support / supporting_methods >= 45:
                matched_events += 1
                if event.impact_level >= 4:
                    strong_matched += 1

        confidence_level = self._initial_confidence(total=total, matched_events=matched_events, strong_matched=strong_matched)
        if clipped_by_birth_date:
            warnings.append("candidate_window_clipped_to_birth_date")
        return CandidateScore(
            candidate_id=candidate_id,
            candidate_time_local=candidate_time_local,
            candidate_window={
                "start": self._shift_minutes(candidate_time_local, -5),
                "end": self._shift_minutes(candidate_time_local, 5),
            },
            scores={
                **per_method_scores,
                "total": total,
            },
            matched_events_count=matched_events,
            strong_events_matched_count=strong_matched,
            confidence_level=confidence_level,
            warnings=sorted(set(warnings)),
            source_asc_interval=source_asc_interval,
            clipped_by_birth_date=clipped_by_birth_date,
        )

    @staticmethod
    def _weighted_total(
        *,
        per_method_scores: dict[str, float | None],
        weights: dict[str, float],
        available_methods: list[str],
    ) -> float:
        if not available_methods:
            return 0.0
        total_weight = sum(float(weights.get(method_name, 0.0)) for method_name in available_methods)
        if total_weight <= 0:
            total_weight = float(len(available_methods))
        acc = 0.0
        for method_name in available_methods:
            score = per_method_scores.get(method_name)
            if score is None:
                continue
            method_weight = float(weights.get(method_name, 0.0)) / total_weight
            if method_weight == 0:
                method_weight = 1.0 / len(available_methods)
            acc += score * method_weight
        return round(acc, 2)

    @staticmethod
    def _initial_confidence(*, total: float, matched_events: int, strong_matched: int) -> str:
        if total >= 75 and matched_events >= 5 and strong_matched >= 3:
            return "high"
        if total >= 55 and matched_events >= 3:
            return "medium"
        return "low"

    @staticmethod
    def _shift_minutes(dt_local_iso: str, delta_minutes: int) -> str:
        from datetime import datetime, timedelta

        base = datetime.fromisoformat(dt_local_iso)
        return (base + timedelta(minutes=delta_minutes)).isoformat(timespec="seconds")
