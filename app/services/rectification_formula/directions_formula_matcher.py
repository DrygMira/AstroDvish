from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Literal

from app.models.event_models import DatePrecision, EventCard
from app.models.formula_card_models import FormulaAspectMatch, FormulaCard, FormulaDirectionRule
from app.models.response_models import ChartResponse
from app.services.rectification_formula.direction_chart_builder import (
    DirectionChartBuildResult,
    DirectionChartBuilder,
    DirectionMethod,
)

ASPECT_MEANINGS: dict[str, str] = {
    "conjunction": "direct activation of the formula link",
    "trine": "easy support and free realization of the formula link",
    "sextile": "working opportunity and activation through action",
    "square": "tension and forced realization of the formula link",
    "opposition": "axis-based event manifestation through polarization",
    "quincunx": "adjustment and uncomfortable reconfiguration of the formula link",
}

ASPECT_ANGLES: dict[str, float] = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "quincunx": 150.0,
    "opposition": 180.0,
}

SIGN_RULERS: dict[str, list[dict[str, str]]] = {
    "Aries": [{"name": "mars", "ruler_type": "primary_ruler"}],
    "Taurus": [{"name": "venus", "ruler_type": "primary_ruler"}],
    "Gemini": [{"name": "mercury", "ruler_type": "primary_ruler"}],
    "Cancer": [{"name": "moon", "ruler_type": "primary_ruler"}],
    "Leo": [{"name": "sun", "ruler_type": "primary_ruler"}],
    "Virgo": [{"name": "mercury", "ruler_type": "primary_ruler"}],
    "Libra": [{"name": "venus", "ruler_type": "primary_ruler"}],
    "Scorpio": [
        {"name": "mars", "ruler_type": "primary_ruler"},
        {"name": "pluto", "ruler_type": "modern_ruler"},
    ],
    "Sagittarius": [{"name": "jupiter", "ruler_type": "primary_ruler"}],
    "Capricorn": [{"name": "saturn", "ruler_type": "primary_ruler"}],
    "Aquarius": [
        {"name": "saturn", "ruler_type": "primary_ruler"},
        {"name": "uranus", "ruler_type": "modern_ruler"},
    ],
    "Pisces": [
        {"name": "jupiter", "ruler_type": "primary_ruler"},
        {"name": "neptune", "ruler_type": "modern_ruler"},
    ],
}


@dataclass(frozen=True)
class ResolvedPoint:
    key: str
    base_key: str
    natal_degree: float
    degree: float
    role: str | None = None
    ruler_type: str | None = None


class DirectionsFormulaMatcher:
    def __init__(self, *, direction_chart_builder: DirectionChartBuilder | None = None) -> None:
        self.direction_chart_builder = direction_chart_builder or DirectionChartBuilder()

    def evaluate(
        self,
        *,
        card: FormulaCard,
        chart: ChartResponse,
        candidate_birth_date: date,
        event: EventCard,
        direction_method: DirectionMethod | None = None,
    ) -> tuple[list[FormulaAspectMatch], list[FormulaAspectMatch], list[dict[str, Any]], list[dict[str, Any]]]:
        event_date = self._event_anchor_date(event)
        if event_date is None:
            missing = [
                {
                    "rule_id": rule.id,
                    "reason": "missing_event_date",
                    "display_formula": self._display_formula(rule),
                }
                for rule in card.direction_rules
                if rule.required
            ]
            return [], [], missing, []

        direction_result = self.direction_chart_builder.build(
            natal_chart=chart,
            candidate_birth_date=candidate_birth_date,
            event=event,
            direction_method=direction_method,
        )

        matched: list[FormulaAspectMatch] = []
        rejected: list[FormulaAspectMatch] = []
        missing_rules: list[dict[str, Any]] = []
        rule_debug: list[dict[str, Any]] = []

        for rule in card.direction_rules:
            rule_result = self._evaluate_rule(
                card=card,
                chart=chart,
                direction_result=direction_result,
                event=event,
                rule=rule,
            )
            matched.extend(rule_result["matched"])
            rejected.extend(rule_result["rejected"])
            missing_rules.extend(rule_result["missing"])
            rule_debug.append(rule_result["debug"])

        matched.sort(key=lambda item: (item.orb, item.directed_point, item.natal_target))
        rejected.sort(key=lambda item: (item.orb, item.directed_point, item.natal_target))
        return matched, rejected, missing_rules, rule_debug

    def _evaluate_rule(
        self,
        *,
        card: FormulaCard,
        chart: ChartResponse,
        direction_result: DirectionChartBuildResult,
        event: EventCard,
        rule: FormulaDirectionRule,
    ) -> dict[str, Any]:
        directed_points = self._resolve_selectors(
            chart=chart,
            card=card,
            selectors=rule.source_selectors,
            coordinate_kind="directed",
            direction_result=direction_result,
        )
        natal_points = self._resolve_selectors(
            chart=chart,
            card=card,
            selectors=rule.target_selectors,
            coordinate_kind="natal",
            direction_result=direction_result,
        )

        debug: dict[str, Any] = {
            "rule_id": rule.id,
            "title": rule.title,
            "display_formula": self._display_formula(rule),
            "priority": rule.priority or rule.priority_tier,
            "role": rule.role,
            "source_kind": "directed",
            "target_kind": "natal",
            "direction_method": direction_result.direction_method,
            "direction_arc": round(direction_result.direction_arc, 6),
            "resolved_sources": [point.key for point in directed_points],
            "resolved_targets": [point.key for point in natal_points],
            "resolved_source_details": [
                {"point_name": point.key, "role": point.role, "ruler_type": point.ruler_type}
                for point in directed_points
            ],
            "resolved_target_details": [
                {"point_name": point.key, "role": point.role, "ruler_type": point.ruler_type}
                for point in natal_points
            ],
            "checked_pairs": [],
            "matched_pairs": [],
            "rejected_pairs": [],
        }
        matched: list[FormulaAspectMatch] = []
        rejected: list[FormulaAspectMatch] = []
        missing: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str, str]] = set()

        if not directed_points:
            if rule.required:
                missing.append(
                    {
                        "rule_id": rule.id,
                        "reason": "unresolved_source",
                        "display_formula": self._display_formula(rule),
                    }
                )
            return {"matched": matched, "rejected": rejected, "missing": missing, "debug": debug}

        if not natal_points:
            if rule.required:
                missing.append(
                    {
                        "rule_id": rule.id,
                        "reason": "unresolved_target",
                        "display_formula": self._display_formula(rule),
                    }
                )
            return {"matched": matched, "rejected": rejected, "missing": missing, "debug": debug}

        for source in directed_points:
            for target in natal_points:
                if source.key == target.key and source.base_key == target.base_key:
                    continue
                aspect_name, orb, actual_angle, exact_angle = self._closest_requested_aspect(
                    source.degree,
                    target.degree,
                    rule.aspect_types,
                )
                if aspect_name is None or orb is None or actual_angle is None or exact_angle is None:
                    continue

                key = (source.key, target.key, aspect_name)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

                pair_payload = {
                    "directed_point": source.key,
                    "natal_target": target.key,
                    "source_role": source.role,
                    "target_role": target.role,
                    "source_ruler_type": source.ruler_type,
                    "target_ruler_type": target.ruler_type,
                    "source_coordinate_type": "directed",
                    "target_coordinate_type": "natal",
                    "source_natal_coordinate": round(source.natal_degree, 4),
                    "directed_coordinate": round(source.degree, 4),
                    "natal_coordinate": round(target.degree, 4),
                    "aspect_type": aspect_name,
                    "actual_angle": round(actual_angle, 4),
                    "exact_angle": round(exact_angle, 4),
                    "orb": round(orb, 4),
                    "orb_limit": round(rule.orb_limit, 4),
                }
                debug["checked_pairs"].append(pair_payload)

                match = FormulaAspectMatch(
                    method="directions",
                    event_type=event.event_type.value,
                    card_id=card.card_id,
                    direction_method=direction_result.direction_method,
                    direction_arc=round(direction_result.direction_arc, 6),
                    directed_point=source.key,
                    directed_point_role=source.role,
                    directed_point_ruler_type=source.ruler_type,
                    directed_source_longitude=round(source.degree, 4),
                    natal_target=target.key,
                    natal_target_role=target.role,
                    natal_target_ruler_type=target.ruler_type,
                    natal_target_longitude=round(target.degree, 4),
                    aspect_type=aspect_name,
                    actual_angle=round(actual_angle, 4),
                    exact_angle=round(exact_angle, 4),
                    orb=round(orb, 4),
                    orb_limit=round(rule.orb_limit, 4),
                    strength=self._strength(orb, rule.orb_limit),
                    match_status="matched" if orb <= rule.orb_limit else "rejected",
                    formula_rule_matched=rule.id,
                    rule_weight=rule.weight,
                    priority_tier=rule.priority_tier,
                    explanation_for_expert=(
                        f"Directed {source.key} -> Natal {target.key}: {aspect_name}; "
                        f"{ASPECT_MEANINGS.get(aspect_name, 'formula link')}."
                    ),
                    rejection_reason=None,
                )

                if orb <= rule.orb_limit:
                    matched.append(match)
                    debug["matched_pairs"].append(pair_payload)
                else:
                    rejected_match = match.model_copy(update={"rejection_reason": "over_orb"})
                    rejected.append(rejected_match)
                    debug["rejected_pairs"].append({**pair_payload, "reason": "over_orb"})

        if rule.required and not matched:
            reason = "over_orb_only" if rejected else "no_matching_aspect"
            missing.append(
                {
                    "rule_id": rule.id,
                    "reason": reason,
                    "display_formula": self._display_formula(rule),
                }
            )

        return {"matched": matched, "rejected": rejected, "missing": missing, "debug": debug}

    def _resolve_selectors(
        self,
        *,
        chart: ChartResponse,
        card: FormulaCard,
        selectors: Iterable[str],
        coordinate_kind: Literal["directed", "natal"],
        direction_result: DirectionChartBuildResult,
    ) -> list[ResolvedPoint]:
        points: dict[str, ResolvedPoint] = {}
        for selector in selectors:
            for point in self._resolve_selector(
                chart=chart,
                card=card,
                selector=selector,
                coordinate_kind=coordinate_kind,
                direction_result=direction_result,
            ):
                points[point.key] = point
        return list(points.values())

    def _resolve_selector(
        self,
        *,
        chart: ChartResponse,
        card: FormulaCard,
        selector: str,
        coordinate_kind: Literal["directed", "natal"],
        direction_result: DirectionChartBuildResult,
    ) -> list[ResolvedPoint]:
        if selector == "significators":
            return self._resolve_selectors(
                chart=chart,
                card=card,
                selectors=card.significators,
                coordinate_kind=coordinate_kind,
                direction_result=direction_result,
            )
        if selector.startswith("cusp_"):
            house_num = selector.split("_", 1)[1]
            point_key = f"cusp_{house_num}"
            return self._point_from_base_key(
                point_key=point_key,
                base_key=point_key,
                direction_result=direction_result,
                coordinate_kind=coordinate_kind,
                role=selector,
            )
        if selector.startswith("ruler_"):
            house_num = selector.split("_", 1)[1]
            return self._resolve_house_rulers(
                chart=chart,
                house_num=house_num,
                coordinate_kind=coordinate_kind,
                direction_result=direction_result,
            )
        if selector.startswith("house_elements_"):
            house_num = int(selector.split("_")[-1])
            return self._resolve_house_elements(
                chart=chart,
                house_num=house_num,
                coordinate_kind=coordinate_kind,
                direction_result=direction_result,
            )
        if selector in {"asc", "mc"}:
            return self._point_from_base_key(
                point_key=selector,
                base_key=selector,
                direction_result=direction_result,
                coordinate_kind=coordinate_kind,
                role=selector,
            )
        if selector in chart.objects:
            return self._point_from_base_key(
                point_key=selector,
                base_key=selector,
                direction_result=direction_result,
                coordinate_kind=coordinate_kind,
                role=selector,
            )
        return []

    def _point_from_base_key(
        self,
        *,
        point_key: str,
        base_key: str,
        direction_result: DirectionChartBuildResult,
        coordinate_kind: Literal["directed", "natal"],
        role: str | None = None,
        ruler_type: str | None = None,
    ) -> list[ResolvedPoint]:
        natal_degree = direction_result.natal_coordinate(base_key)
        degree = self._coordinate(direction_result=direction_result, base_key=base_key, coordinate_kind=coordinate_kind)
        if natal_degree is None or degree is None:
            return []
        return [
            ResolvedPoint(
                key=point_key,
                base_key=base_key,
                natal_degree=float(natal_degree),
                degree=float(degree),
                role=role,
                ruler_type=ruler_type,
            )
        ]

    def _resolve_house_rulers(
        self,
        *,
        chart: ChartResponse,
        house_num: str,
        coordinate_kind: Literal["directed", "natal"],
        direction_result: DirectionChartBuildResult,
    ) -> list[ResolvedPoint]:
        cusp = chart.houses.cusp_details.get(str(house_num))
        if cusp is None:
            return []
        rulers = SIGN_RULERS.get(cusp.sign_name_en, [])
        points: list[ResolvedPoint] = []
        for ruler_info in rulers:
            ruler_name = ruler_info["name"]
            ruler_type = ruler_info["ruler_type"]
            points.extend(
                self._point_from_base_key(
                    point_key=f"ruler_{house_num}:{ruler_name}",
                    base_key=ruler_name,
                    direction_result=direction_result,
                    coordinate_kind=coordinate_kind,
                    role=f"ruler_{house_num}",
                    ruler_type=ruler_type,
                )
            )
        return points

    def _resolve_house_elements(
        self,
        *,
        chart: ChartResponse,
        house_num: int,
        coordinate_kind: Literal["directed", "natal"],
        direction_result: DirectionChartBuildResult,
    ) -> list[ResolvedPoint]:
        points: list[ResolvedPoint] = []
        for name, obj in chart.objects.items():
            if obj.house != house_num:
                continue
            points.extend(
                self._point_from_base_key(
                    point_key=f"house_element_{house_num}:{name}",
                    base_key=name,
                    direction_result=direction_result,
                    coordinate_kind=coordinate_kind,
                    role=f"house_element_{house_num}",
                )
            )
        return points

    @staticmethod
    def _coordinate(
        *,
        direction_result: DirectionChartBuildResult,
        base_key: str,
        coordinate_kind: Literal["directed", "natal"],
    ) -> float | None:
        if coordinate_kind == "directed":
            return direction_result.directed_coordinate(base_key)
        return direction_result.natal_coordinate(base_key)

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
    def _angular_distance(left: float, right: float) -> float:
        delta = abs(left - right) % 360.0
        return min(delta, 360.0 - delta)

    def _closest_requested_aspect(
        self,
        source_degree: float,
        target_degree: float,
        aspect_types: Iterable[str],
    ) -> tuple[str | None, float | None, float | None, float | None]:
        delta = self._angular_distance(source_degree, target_degree)
        best_name: str | None = None
        best_orb: float | None = None
        best_exact: float | None = None
        for aspect_type in aspect_types:
            exact = ASPECT_ANGLES.get(aspect_type)
            if exact is None:
                continue
            orb = abs(delta - exact)
            if best_orb is None or orb < best_orb:
                best_name = aspect_type
                best_orb = orb
                best_exact = exact
        return best_name, best_orb, delta, best_exact

    @staticmethod
    def _strength(orb: float, orb_limit: float) -> str:
        if orb <= 0.2:
            return "exact"
        if orb <= min(0.5, orb_limit * 0.35):
            return "strong"
        if orb <= orb_limit:
            return "working"
        return "weak"

    @staticmethod
    def _display_formula(rule: FormulaDirectionRule) -> str:
        if rule.formula:
            return rule.formula
        source = rule.display_source or ", ".join(rule.source_selectors) or "source"
        target = rule.display_target or ", ".join(rule.target_selectors) or "target"
        return f"Directed {source} -> Natal {target}"
