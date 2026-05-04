from __future__ import annotations

from app.models.event_models import DatePrecision, EventCard
from app.models.rectification_pro_models import CandidateScore, ConfidenceSummary


class ConfidenceService:
    def summarize(
        self,
        *,
        best_candidate: CandidateScore | None,
        events: list[EventCard],
    ) -> ConfidenceSummary:
        if best_candidate is None:
            return ConfidenceSummary(
                level="low",
                time_window_minutes=240,
                explanation="Нет валидных кандидатов времени. Требуются Asc-окна и события.",
            )

        exact_events = sum(1 for item in events if item.date_precision == DatePrecision.exact and item.start_date)
        strong_events = sum(1 for item in events if item.impact_level >= 4)
        method_strength = sum(
            1
            for name in ("directions", "solar", "transits", "lunar")
            if isinstance(best_candidate.scores.get(name), (int, float))
            and float(best_candidate.scores[name] or 0.0) >= 55
        )

        if (
            best_candidate.confidence_level == "high"
            and len(events) >= 5
            and strong_events >= 3
            and exact_events >= 3
            and method_strength >= 2
            and best_candidate.matched_events_count >= 5
        ):
            return ConfidenceSummary(
                level="expert_high",
                time_window_minutes=5,
                explanation="Сильные точные события подтверждены минимум двумя методиками. Допустимо окно около 5 минут.",
            )

        if best_candidate.confidence_level == "high":
            return ConfidenceSummary(
                level="high",
                time_window_minutes=10,
                explanation="Есть многометодные подтверждения и устойчивое лучшее окно 5–10 минут.",
            )

        if best_candidate.confidence_level == "medium":
            return ConfidenceSummary(
                level="medium",
                time_window_minutes=25,
                explanation="Есть рабочие подтверждения, но данных пока недостаточно для точности 5–10 минут.",
            )

        return ConfidenceSummary(
            level="low",
            time_window_minutes=120,
            explanation="Событий или точных дат недостаточно для узкого окна времени.",
        )
