from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.models.event_models import DatePrecision, EventCard
from app.models.rectification_pro_models import MethodMatch
from app.models.response_models import ChartResponse

MAJOR_ASPECTS: dict[str, float] = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "opposition": 180.0,
}


class DirectionsService:
    def evaluate_candidate(
        self,
        *,
        candidate_chart: ChartResponse,
        candidate_birth_date: date,
        events: list[EventCard],
        directions_orbs: dict[str, float],
    ) -> list[MethodMatch]:
        result: list[MethodMatch] = []
        default_orb = float(directions_orbs.get("default", 1.0))
        for event in events:
            event_date = self._event_anchor_date(event)
            if event_date is None:
                result.append(
                    MethodMatch(
                        event_id=event.event_id,
                        method="directions",
                        event_score=0.0,
                        warnings=["event_date_unknown_for_directions"],
                    )
                )
                continue

            age_years = (event_date - candidate_birth_date).days / 365.2425
            if age_years < 0:
                result.append(
                    MethodMatch(
                        event_id=event.event_id,
                        method="directions",
                        event_score=0.0,
                        warnings=["event_before_birth_date"],
                    )
                )
                continue

            symbolic_arc = age_years % 360.0
            directed_points = self._directed_points(candidate_chart, symbolic_arc)
            matches: list[dict[str, Any]] = []
            for directed_name, directed_degree in directed_points.items():
                for natal_name, natal_obj in candidate_chart.objects.items():
                    orb_match = self._match_aspect(
                        directed_degree=float(directed_degree),
                        natal_degree=float(natal_obj.absolute_degree_0_360),
                        orb_limit=default_orb,
                    )
                    if orb_match is None:
                        continue
                    aspect_type, orb = orb_match
                    score = max(0.0, 100.0 - orb * 40.0)
                    matches.append(
                        {
                            "directed_object": directed_name,
                            "natal_object": natal_name,
                            "aspect_type": aspect_type,
                            "orb": round(orb, 4),
                            "score": round(score, 2),
                            "explanation": f"Directed {directed_name} {aspect_type} natal {natal_name}",
                        }
                    )

            event_score = self._event_score(matches=matches, impact_level=event.impact_level)
            result.append(
                MethodMatch(
                    event_id=event.event_id,
                    method="directions",
                    matches=sorted(matches, key=lambda item: item["orb"])[:25],
                    event_score=event_score,
                )
            )
        return result

    @staticmethod
    def _event_anchor_date(event: EventCard) -> date | None:
        if event.start_date:
            return date.fromisoformat(event.start_date)
        if event.date_precision == DatePrecision.exact and event.date_text:
            try:
                return date.fromisoformat(event.date_text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _directed_points(chart: ChartResponse, symbolic_arc: float) -> dict[str, float]:
        directed: dict[str, float] = {}
        for name, obj in chart.objects.items():
            directed[name] = (obj.absolute_degree_0_360 + symbolic_arc) % 360.0
        for house_num, cusp in chart.houses.cusps.items():
            directed[f"cusp_{house_num}"] = (float(cusp) + symbolic_arc) % 360.0
        if "mc" in chart.angles:
            directed["MC"] = (float(chart.angles["mc"]) + symbolic_arc) % 360.0
        if "asc" in chart.angles:
            directed["Asc"] = (float(chart.angles["asc"]) + symbolic_arc) % 360.0
        return directed

    @staticmethod
    def _angular_distance(left: float, right: float) -> float:
        delta = abs(left - right) % 360.0
        return min(delta, 360.0 - delta)

    def _match_aspect(self, *, directed_degree: float, natal_degree: float, orb_limit: float) -> tuple[str, float] | None:
        delta = self._angular_distance(directed_degree, natal_degree)
        best: tuple[str, float] | None = None
        for aspect_name, exact in MAJOR_ASPECTS.items():
            orb = abs(delta - exact)
            if orb > orb_limit:
                continue
            if best is None or orb < best[1]:
                best = (aspect_name, orb)
        return best

    @staticmethod
    def _event_score(*, matches: list[dict[str, Any]], impact_level: int) -> float:
        if not matches:
            return 0.0
        top = sorted(matches, key=lambda item: float(item["score"]), reverse=True)[:5]
        avg = sum(float(item["score"]) for item in top) / len(top)
        impact_multiplier = 0.75 + (impact_level / 10.0)
        return round(min(100.0, avg * impact_multiplier), 2)
