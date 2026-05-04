from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.event_models import EventCard
from app.models.rectification_pro_models import MethodMatch
from app.models.response_models import ChartResponse


class SolarService:
    def evaluate_candidate(
        self,
        *,
        candidate_chart: ChartResponse,
        events: list[EventCard],
    ) -> list[MethodMatch]:
        result: list[MethodMatch] = []
        natal_sun = candidate_chart.objects.get("sun")
        if natal_sun is None:
            return [
                MethodMatch(
                    event_id=event.event_id,
                    method="solar",
                    warnings=["missing_natal_sun_for_solar_validation"],
                    event_score=0.0,
                )
                for event in events
            ]

        for event in events:
            event_year = self._event_year(event)
            if event_year is None:
                result.append(
                    MethodMatch(
                        event_id=event.event_id,
                        method="solar",
                        warnings=["event_year_unknown_for_solar"],
                        event_score=0.0,
                    )
                )
                continue

            # MVP proxy: assess how close annual-solar anchor is to angular points.
            annual_shift = (event_year - date.fromisoformat(candidate_chart.input.datetime_utc[:10]).year) % 360
            solar_sun = (natal_sun.absolute_degree_0_360 + annual_shift) % 360.0
            asc = candidate_chart.angles.get("asc")
            mc = candidate_chart.angles.get("mc")
            matches: list[dict[str, object]] = []
            if isinstance(asc, (int, float)):
                orb = self._orb(solar_sun, float(asc))
                matches.append({"solar_point": "Sun", "target": "Asc", "orb": round(orb, 4)})
            if isinstance(mc, (int, float)):
                orb = self._orb(solar_sun, float(mc))
                matches.append({"solar_point": "Sun", "target": "MC", "orb": round(orb, 4)})

            best_orb = min((float(item["orb"]) for item in matches), default=30.0)
            score = max(0.0, 100.0 - best_orb * 2.0)
            result.append(
                MethodMatch(
                    event_id=event.event_id,
                    method="solar",
                    matches=matches,
                    event_score=round(score, 2),
                )
            )
        return result

    @staticmethod
    def _event_year(event: EventCard) -> int | None:
        if event.start_date:
            return date.fromisoformat(event.start_date).year
        if event.date_text and len(event.date_text) >= 4 and event.date_text[:4].isdigit():
            return int(event.date_text[:4])
        return None

    @staticmethod
    def _orb(left: float, right: float) -> float:
        delta = abs(left - right) % 360.0
        return min(delta, 360.0 - delta)
