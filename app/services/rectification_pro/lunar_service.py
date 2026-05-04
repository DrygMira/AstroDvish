from __future__ import annotations

from app.models.event_models import EventCard
from app.models.rectification_pro_models import MethodMatch
from app.models.response_models import ChartResponse


class LunarService:
    def evaluate_candidate(
        self,
        *,
        candidate_chart: ChartResponse,
        events: list[EventCard],
        include_lunars: bool,
    ) -> list[MethodMatch]:
        if not include_lunars:
            return []

        # MVP placeholder: provide bounded response without heavy monthly sweep.
        return [
            MethodMatch(
                event_id=event.event_id,
                method="lunar",
                event_score=0.0,
                warnings=["lunar_mvp_placeholder_nearest_cycle_not_implemented"],
            )
            for event in events
        ]
