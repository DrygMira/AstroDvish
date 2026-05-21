from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from app.models.event_models import EventCard
from app.models.formula_card_models import FormulaAspectMatch, FormulaCard, FormulaDirectionRule
from app.models.response_models import ChartResponse
from app.services.rectification_pro.directions_service import DirectionsService

ASPECT_MEANINGS: dict[str, str] = {
    "conjunction": "прямое соединение и явная активация формулы",
    "trine": "естественная поддержка и свободная реализация формулы",
    "sextile": "рабочая возможность и включение формулы через действие",
    "square": "напряжение и вынужденная реализация формулы",
    "opposition": "поляризация и событийное проявление через ось",
    "quincunx": "перестройка и неудобная подстройка формулы",
}

ASPECT_ANGLES: dict[str, float] = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "quincunx": 150.0,
    "opposition": 180.0,
}

SIGN_RULERS: dict[str, list[str]] = {
    "Aries": ["mars"],
    "Taurus": ["venus"],
    "Gemini": ["mercury"],
    "Cancer": ["moon"],
    "Leo": ["sun"],
    "Virgo": ["mercury"],
    "Libra": ["venus"],
    "Scorpio": ["mars", "pluto"],
    "Sagittarius": ["jupiter"],
    "Capricorn": ["saturn"],
    "Aquarius": ["saturn", "uranus"],
    "Pisces": ["jupiter", "neptune"],
}


@dataclass(frozen=True)
class ResolvedPoint:
    key: str
    degree: float


class DirectionsFormulaMatcher:
    def __init__(self) -> None:
        self._directions = DirectionsService()

    def evaluate(
        self,
        *,
        card: FormulaCard,
        chart: ChartResponse,
        candidate_birth_date: date,
        event: EventCard,
    ) -> tuple[list[FormulaAspectMatch], list[FormulaAspectMatch], list[str]]:
        event_date = self._directions._event_anchor_date(event)
        if event_date is None:
            return [], [], [rule.id for rule in card.direction_rules if rule.required]

        symbolic_arc = ((event_date - candidate_birth_date).days / 365.2425) % 360.0
        matched: list[FormulaAspectMatch] = []
        rejected: list[FormulaAspectMatch] = []
        missing_rules: list[str] = []

        for rule in card.direction_rules:
            rule_matches = self._evaluate_rule(
                card=card,
                chart=chart,
                symbolic_arc=symbolic_arc,
                event=event,
                rule=rule,
            )
            if rule_matches["matched"]:
                matched.extend(rule_matches["matched"])
            if rule_matches["rejected"]:
                rejected.extend(rule_matches["rejected"])
            if rule.required and not rule_matches["matched"]:
                missing_rules.append(rule.id)

        matched.sort(key=lambda item: (item.orb, item.directed_point, item.natal_target))
        rejected.sort(key=lambda item: (item.orb, item.directed_point, item.natal_target))
        return matched, rejected, missing_rules

    def _evaluate_rule(
        self,
        *,
        card: FormulaCard,
        chart: ChartResponse,
        symbolic_arc: float,
        event: EventCard,
        rule: FormulaDirectionRule,
    ) -> dict[str, list[FormulaAspectMatch]]:
        directed_points = self._resolve_selectors(
            chart=chart,
            card=card,
            selectors=rule.source_selectors,
            directed=True,
            symbolic_arc=symbolic_arc,
        )
        natal_points = self._resolve_selectors(
            chart=chart,
            card=card,
            selectors=rule.target_selectors,
            directed=False,
            symbolic_arc=symbolic_arc,
        )
        matched: list[FormulaAspectMatch] = []
        rejected: list[FormulaAspectMatch] = []

        seen_pairs: set[tuple[str, str, str]] = set()
        for source in directed_points:
            for target in natal_points:
                if source.key == target.key:
                    continue
                best_aspect, best_orb = self._closest_requested_aspect(
                    source.degree,
                    target.degree,
                    rule.aspect_types,
                )
                if best_aspect is None or best_orb is None:
                    continue
                strength = self._strength(best_orb, rule.orb_limit)
                match = FormulaAspectMatch(
                    method="directions",
                    event_type=event.event_type.value,
                    card_id=card.card_id,
                    directed_point=source.key,
                    natal_target=target.key,
                    aspect_type=best_aspect,
                    orb=round(best_orb, 4),
                    strength=strength,
                    formula_rule_matched=rule.id,
                    explanation_for_expert=(
                        f"Направленная точка {source.key} образует {best_aspect} к {target.key}; "
                        f"{ASPECT_MEANINGS.get(best_aspect, 'формульная связь')}."
                    ),
                )
                key = (source.key, target.key, best_aspect)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                if best_orb <= rule.orb_limit:
                    matched.append(match)
                else:
                    rejected.append(match)
        return {"matched": matched, "rejected": rejected}

    def _resolve_selectors(
        self,
        *,
        chart: ChartResponse,
        card: FormulaCard,
        selectors: Iterable[str],
        directed: bool,
        symbolic_arc: float,
    ) -> list[ResolvedPoint]:
        points: list[ResolvedPoint] = []
        for selector in selectors:
            points.extend(self._resolve_selector(chart=chart, card=card, selector=selector, directed=directed, symbolic_arc=symbolic_arc))
        deduped: dict[str, ResolvedPoint] = {}
        for point in points:
            deduped[point.key] = point
        return list(deduped.values())

    def _resolve_selector(
        self,
        *,
        chart: ChartResponse,
        card: FormulaCard,
        selector: str,
        directed: bool,
        symbolic_arc: float,
    ) -> list[ResolvedPoint]:
        if selector == "significators":
            return self._resolve_selectors(
                chart=chart,
                card=card,
                selectors=card.significators,
                directed=directed,
                symbolic_arc=symbolic_arc,
            )
        if selector.startswith("cusp_"):
            house_num = selector.split("_", 1)[1]
            degree = chart.houses.cusps.get(house_num)
            if degree is None:
                return []
            key = f"cusp_{house_num}"
            return [ResolvedPoint(key=key, degree=self._direct(degree, symbolic_arc, directed))]
        if selector.startswith("ruler_"):
            house_num = selector.split("_", 1)[1]
            return self._resolve_house_rulers(chart=chart, house_num=house_num, directed=directed, symbolic_arc=symbolic_arc)
        if selector.startswith("house_elements_"):
            house_num = int(selector.split("_")[-1])
            return self._resolve_house_elements(chart=chart, house_num=house_num, directed=directed, symbolic_arc=symbolic_arc)
        if selector in {"asc", "mc"}:
            degree = chart.angles.get(selector)
            if degree is None:
                return []
            return [ResolvedPoint(key=selector, degree=self._direct(degree, symbolic_arc, directed))]
        obj = chart.objects.get(selector)
        if obj is not None:
            return [ResolvedPoint(key=selector, degree=self._direct(obj.absolute_degree_0_360, symbolic_arc, directed))]
        return []

    def _resolve_house_rulers(
        self,
        *,
        chart: ChartResponse,
        house_num: str,
        directed: bool,
        symbolic_arc: float,
    ) -> list[ResolvedPoint]:
        cusp = chart.houses.cusp_details.get(str(house_num))
        if cusp is None:
            return []
        rulers = SIGN_RULERS.get(cusp.sign_name_en, [])
        points: list[ResolvedPoint] = []
        for ruler_name in rulers:
            obj = chart.objects.get(ruler_name)
            if obj is None:
                continue
            points.append(
                ResolvedPoint(
                    key=f"ruler_{house_num}:{ruler_name}",
                    degree=self._direct(obj.absolute_degree_0_360, symbolic_arc, directed),
                )
            )
        return points

    def _resolve_house_elements(
        self,
        *,
        chart: ChartResponse,
        house_num: int,
        directed: bool,
        symbolic_arc: float,
    ) -> list[ResolvedPoint]:
        points: list[ResolvedPoint] = []
        for name, obj in chart.objects.items():
            if obj.house != house_num:
                continue
            points.append(
                ResolvedPoint(
                    key=f"house_element_{house_num}:{name}",
                    degree=self._direct(obj.absolute_degree_0_360, symbolic_arc, directed),
                )
            )
        return points

    @staticmethod
    def _direct(degree: float, symbolic_arc: float, directed: bool) -> float:
        return (float(degree) + symbolic_arc) % 360.0 if directed else float(degree)

    @staticmethod
    def _angular_distance(left: float, right: float) -> float:
        delta = abs(left - right) % 360.0
        return min(delta, 360.0 - delta)

    def _closest_requested_aspect(
        self,
        source_degree: float,
        target_degree: float,
        aspect_types: Iterable[str],
    ) -> tuple[str | None, float | None]:
        delta = self._angular_distance(source_degree, target_degree)
        best_name: str | None = None
        best_orb: float | None = None
        for aspect_type in aspect_types:
            exact = ASPECT_ANGLES.get(aspect_type)
            if exact is None:
                continue
            orb = abs(delta - exact)
            if best_orb is None or orb < best_orb:
                best_name = aspect_type
                best_orb = orb
        return best_name, best_orb

    @staticmethod
    def _strength(orb: float, orb_limit: float) -> str:
        if orb <= 0.2:
            return "exact"
        if orb <= min(0.5, orb_limit * 0.35):
            return "strong"
        if orb <= orb_limit:
            return "working"
        return "weak"
