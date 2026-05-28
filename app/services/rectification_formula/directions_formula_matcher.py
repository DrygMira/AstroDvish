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
MAJOR_ASPECTS: tuple[str, ...] = ("conjunction", "sextile", "square", "trine", "opposition")

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
        candidate_birth_datetime_local: str | None = None,
        candidate_birth_datetime_utc: str | None = None,
        timezone_used: str | None = None,
        timezone_offset_used: str | None = None,
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
            candidate_birth_datetime_local=candidate_birth_datetime_local,
            candidate_birth_datetime_utc=candidate_birth_datetime_utc,
            timezone_used=timezone_used,
            timezone_offset_used=timezone_offset_used,
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
        source_selectors, source_selector_decisions = self._effective_selectors(rule=rule, selectors=rule.source_selectors, field_value=rule.source)
        target_selectors, target_selector_decisions = self._effective_selectors(rule=rule, selectors=rule.target_selectors, field_value=rule.target)

        directed_points, source_groups = self._resolve_selectors(
            chart=chart,
            card=card,
            selectors=source_selectors,
            coordinate_kind="directed",
            direction_result=direction_result,
            rule=rule,
        )
        natal_points, target_groups = self._resolve_selectors(
            chart=chart,
            card=card,
            selectors=target_selectors,
            coordinate_kind="natal",
            direction_result=direction_result,
            rule=rule,
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
            "event_date_used": direction_result.event_datetime_used,
            "candidate_birth_datetime_local": direction_result.candidate_birth_datetime_local,
            "candidate_birth_datetime_utc": direction_result.candidate_birth_datetime_utc,
            "timezone_used": direction_result.timezone_used,
            "resolved_sources": [point.key for point in directed_points],
            "resolved_targets": [point.key for point in natal_points],
            "resolved_source_group": source_groups,
            "resolved_target_group": target_groups,
            "resolved_source_groups": source_groups,
            "resolved_target_groups": target_groups,
            "source_selector_decisions": source_selector_decisions,
            "target_selector_decisions": target_selector_decisions,
            "resolved_source_details": [
                {
                    "point_name": point.key,
                    "role": point.role,
                    "ruler_type": point.ruler_type,
                    "weight": rule.weight,
                }
                for point in directed_points
            ],
            "resolved_target_details": [
                {
                    "point_name": point.key,
                    "role": point.role,
                    "ruler_type": point.ruler_type,
                    "weight": rule.weight,
                }
                for point in natal_points
            ],
            "checked_pairs": [],
            "matched_pairs": [],
            "rejected_pairs": [],
            "warnings": [],
        }
        debug["source_ruler_resolution"] = self._build_ruler_resolution_debug(
            chart=chart,
            selectors=source_selectors,
            resolved_points=directed_points,
            allowed_ruler_types=rule.allowed_ruler_types,
            rule_weight=rule.weight,
        )
        debug["target_ruler_resolution"] = self._build_ruler_resolution_debug(
            chart=chart,
            selectors=target_selectors,
            resolved_points=natal_points,
            allowed_ruler_types=rule.allowed_ruler_types,
            rule_weight=rule.weight,
        )
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
                    "source_type": self._point_type(source.key),
                    "target_type": self._point_type(target.key),
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
                    closest_major_name, closest_major_orb, _, closest_major_exact = self._closest_requested_aspect(
                        source.degree,
                        target.degree,
                        MAJOR_ASPECTS,
                    )
                    rejected_payload = {**pair_payload, "reason": "over_orb"}
                    if closest_major_name and closest_major_name not in rule.aspect_types:
                        rejected_payload["closest_major_aspect"] = closest_major_name
                        rejected_payload["closest_major_orb"] = round(float(closest_major_orb or 0.0), 4)
                        rejected_payload["closest_major_exact_angle"] = round(float(closest_major_exact or 0.0), 4)
                    debug["rejected_pairs"].append(rejected_payload)

        if rule.required and not matched:
            reason = "over_orb_only" if rejected else "no_matching_aspect"
            mismatch_hint = self._rule_aspect_mismatch_hint(rule=rule, debug=debug)
            if mismatch_hint:
                reason = "closest_major_aspect_mismatch"
                debug["warnings"].append(mismatch_hint)
            missing.append(
                {
                    "rule_id": rule.id,
                    "reason": reason,
                    "display_formula": self._display_formula(rule),
                    "details": mismatch_hint,
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
        rule: FormulaDirectionRule,
    ) -> tuple[list[ResolvedPoint], dict[str, list[str]]]:
        points: dict[str, ResolvedPoint] = {}
        groups: dict[str, list[str]] = {}
        for selector in selectors:
            resolved_keys: list[str] = []
            for point in self._resolve_selector(
                chart=chart,
                card=card,
                selector=selector,
                coordinate_kind=coordinate_kind,
                direction_result=direction_result,
                rule=rule,
            ):
                points[point.key] = point
                resolved_keys.append(point.key)
            groups[selector] = sorted(dict.fromkeys(resolved_keys))
        return list(points.values()), groups

    def _resolve_selector(
        self,
        *,
        chart: ChartResponse,
        card: FormulaCard,
        selector: str,
        coordinate_kind: Literal["directed", "natal"],
        direction_result: DirectionChartBuildResult,
        rule: FormulaDirectionRule,
    ) -> list[ResolvedPoint]:
        if selector == "significators":
            points, _ = self._resolve_selectors(
                chart=chart,
                card=card,
                selectors=card.significators,
                coordinate_kind=coordinate_kind,
                direction_result=direction_result,
                rule=rule,
            )
            return points
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
                allowed_ruler_types=rule.allowed_ruler_types,
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
        allowed_ruler_types: list[str],
    ) -> list[ResolvedPoint]:
        cusp = chart.houses.cusp_details.get(str(house_num))
        if cusp is None:
            return []
        rulers = SIGN_RULERS.get(cusp.sign_name_en, [])
        points: list[ResolvedPoint] = []
        for ruler_info in rulers:
            ruler_name = ruler_info["name"]
            ruler_type = ruler_info["ruler_type"]
            if allowed_ruler_types and ruler_type not in allowed_ruler_types:
                continue
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

    @staticmethod
    def _point_type(point_key: str) -> str:
        if point_key.startswith("cusp_"):
            return "cusp"
        if point_key.startswith("house_element_"):
            return "house_element"
        if point_key.startswith("ruler_"):
            return "ruler"
        return "planet_or_point"

    @staticmethod
    def _rule_aspect_mismatch_hint(*, rule: FormulaDirectionRule, debug: dict[str, Any]) -> dict[str, Any] | None:
        rejected_pairs = debug.get("rejected_pairs") or []
        if not rejected_pairs:
            return None
        with_major = [pair for pair in rejected_pairs if pair.get("closest_major_aspect")]
        if not with_major:
            return None
        best = sorted(with_major, key=lambda item: float(item.get("closest_major_orb", 999.0)))[0]
        return {
            "rule_id": rule.id,
            "configured_aspects": list(rule.aspect_types),
            "closest_major_aspect": best.get("closest_major_aspect"),
            "closest_major_orb": best.get("closest_major_orb"),
            "closest_major_exact_angle": best.get("closest_major_exact_angle"),
            "actual_angle": best.get("actual_angle"),
        }

    @classmethod
    def _effective_selectors(
        cls,
        *,
        rule: FormulaDirectionRule,
        selectors: list[str],
        field_value: str | None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        if not selectors:
            return [], []
        if not field_value:
            return selectors, [{"selector": item, "status": "included", "reason": "no_literal_filter"} for item in selectors]
        requested_tokens = [item.strip().lower() for item in str(field_value).split(",") if item.strip()]
        if not requested_tokens:
            return selectors, [{"selector": item, "status": "included", "reason": "empty_literal_filter"} for item in selectors]
        effective: list[str] = []
        decisions: list[dict[str, Any]] = []
        for selector in selectors:
            normalized = selector.strip().lower()
            aliases = cls._selector_aliases(normalized)
            is_allowed = any(token in aliases for token in requested_tokens)
            if is_allowed:
                effective.append(selector)
                decisions.append(
                    {
                        "selector": selector,
                        "status": "included",
                        "reason": "literal_match",
                        "include_reason": "literal_match",
                        "exclude_reason": None,
                        "literal": field_value,
                    }
                )
            else:
                decisions.append(
                    {
                        "selector": selector,
                        "status": "excluded",
                        "reason": "literal_filter_mismatch",
                        "include_reason": None,
                        "exclude_reason": "literal_filter_mismatch",
                        "literal": field_value,
                    }
                )
        if not effective:
            return selectors, decisions
        return effective, decisions

    @staticmethod
    def _selector_aliases(token: str) -> set[str]:
        aliases = {token}
        if token.startswith("house_element_"):
            aliases.add(token.replace("house_element_", "house_elements_", 1))
        if token.startswith("house_elements_"):
            aliases.add(token.replace("house_elements_", "house_element_", 1))
        if token in {"sun", "moon", "jupiter", "venus", "mars", "mercury", "saturn", "uranus", "neptune", "pluto", "chiron", "proserpina", "lilith", "selena"}:
            aliases.add("significators")
        return aliases

    @classmethod
    def _build_ruler_resolution_debug(
        cls,
        *,
        chart: ChartResponse,
        selectors: Iterable[str],
        resolved_points: list[ResolvedPoint],
        allowed_ruler_types: list[str],
        rule_weight: float,
    ) -> list[dict[str, Any]]:
        resolved_keys = {item.key for item in resolved_points}
        debug_items: list[dict[str, Any]] = []
        for selector in selectors:
            if not selector.startswith("ruler_"):
                continue
            house_num = selector.split("_", 1)[1]
            cusp = chart.houses.cusp_details.get(str(house_num))
            if cusp is None:
                debug_items.append(
                    {
                        "selector": selector,
                        "status": "excluded",
                        "exclude_reason": "missing_cusp",
                    }
                )
                continue
            for candidate in SIGN_RULERS.get(cusp.sign_name_en, []):
                point_key = f"ruler_{house_num}:{candidate['name']}"
                ruler_type = candidate["ruler_type"]
                if allowed_ruler_types and ruler_type not in allowed_ruler_types:
                    debug_items.append(
                        {
                            "selector": selector,
                            "point_name": point_key,
                            "ruler_type": ruler_type,
                            "weight": rule_weight,
                            "status": "excluded",
                            "include_reason": None,
                            "exclude_reason": "ruler_type_not_allowed",
                            "allowed_ruler_types": list(allowed_ruler_types),
                        }
                    )
                    continue
                debug_items.append(
                    {
                        "selector": selector,
                        "point_name": point_key,
                        "ruler_type": ruler_type,
                        "weight": rule_weight,
                        "status": "included" if point_key in resolved_keys else "excluded",
                        "include_reason": "cusp_sign_ruler_match" if point_key in resolved_keys else None,
                        "exclude_reason": None if point_key in resolved_keys else "point_not_present_in_chart",
                        "allowed_ruler_types": list(allowed_ruler_types),
                    }
                )
        return debug_items

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
