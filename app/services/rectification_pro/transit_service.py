from __future__ import annotations

from datetime import date

from app.models.event_models import DatePrecision, EventCard
from app.models.rectification_pro_models import MethodMatch
from app.models.response_models import ChartResponse


class TransitService:
    def evaluate_candidate(
        self,
        *,
        candidate_chart: ChartResponse,
        events: list[EventCard],
    ) -> list[MethodMatch]:
        result: list[MethodMatch] = []
        for event in events:
            if event.date_precision != DatePrecision.exact:
                result.append(
                    MethodMatch(
                        event_id=event.event_id,
                        method="transits",
                        event_score=0.0,
                        warnings=["non_exact_date_low_weight_transit_check_skipped"],
                    )
                )
                continue
            if not event.start_date:
                result.append(
                    MethodMatch(
                        event_id=event.event_id,
                        method="transits",
                        event_score=0.0,
                        warnings=["missing_exact_date_for_transit_check"],
                    )
                )
                continue

            event_date = date.fromisoformat(event.start_date)
            birth_date = date.fromisoformat(candidate_chart.input.datetime_utc[:10])
            days = (event_date - birth_date).days
            # Lightweight deterministic approximation for MVP weighting.
            saturn_natal = candidate_chart.objects.get("saturn")
            mc = candidate_chart.angles.get("mc")
            if saturn_natal is None or not isinstance(mc, (int, float)):
                result.append(
                    MethodMatch(
                        event_id=event.event_id,
                        method="transits",
                        event_score=0.0,
                        warnings=["missing_saturn_or_mc_for_transit_check"],
                    )
                )
                continue

            saturn_transit = (saturn_natal.absolute_degree_0_360 + days * 0.0334) % 360.0
            delta = self._orb(saturn_transit, float(mc))
            score = max(0.0, 100.0 - delta * 3.0)
            match = {
                "transit_object": "Saturn",
                "natal_object": "MC",
                "aspect_type": self._nearest_aspect(delta),
                "orb": round(delta, 4),
                "score": round(score, 2),
            }
            result.append(
                MethodMatch(
                    event_id=event.event_id,
                    method="transits",
                    matches=[match],
                    event_score=round(score, 2),
                )
            )
        return result

    @staticmethod
    def _orb(left: float, right: float) -> float:
        delta = abs(left - right) % 360.0
        return min(delta, 360.0 - delta)

    @staticmethod
    def _nearest_aspect(delta: float) -> str:
        aspects = {
            "conjunction": abs(delta - 0.0),
            "sextile": abs(delta - 60.0),
            "square": abs(delta - 90.0),
            "trine": abs(delta - 120.0),
            "opposition": abs(delta - 180.0),
        }
        return min(aspects, key=aspects.get)
