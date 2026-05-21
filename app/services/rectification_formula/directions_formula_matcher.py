from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from app.models.event_models import DatePrecision, EventCard
from app.models.formula_card_models import FormulaAspectMatch, FormulaCard, FormulaDirectionRule
from app.models.response_models import ChartResponse

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
    def evaluate(
        self,
        *,
        card: FormulaCard,
        chart: ChartResponse,
        candidate_birth_date: date,
        event: EventCard,
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

        symbolic_arc = ((event_date - candidate_birth_date).days / 365.2425) % 360.0
        matched: list[FormulaAspectMatch] = []
        rejected: list[FormulaAspectMatch] = []
        missing_rules: list[dict[str, Any]] = []
        rule_debug: list[dict[str, Any]] = []

        for rule in card.direction_rules:
            rule_result = self._evaluate_rule(
                card=card,
                chart=chart,
                symbolic_arc=symbolic_arc,
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
        symbolic_arc: float,
        event: EventCard,
        rule: FormulaDirectionRule,
    ) -> dict[str, Any]:
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

        debug: dict[str, Any] = {
            "rule_id": rule.id,
            "title": rule.title,
            "display_formula": self._display_formula(rule),
            "source_kind": rule.source_kind,
            "target_kind": rule.target_kind,
            "resolved_sources": [point.key for point in directed_points],
            "resolved_targets": [point.key for point in natal_points],
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
                if source.key == target.key:
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
                    "aspect_type": aspect_name,
                    "actual_angle": round(actual_angle, 4),
                    "exact_angle": round(exact_angle, 4),
                    "orb": round(orb, 4),
                    "limit": round(rule.orb_limit, 4),
                }
                debug["checked_pairs"].append(pair_payload)

                match = FormulaAspectMatch(
                    method="directions",
                    event_type=event.event_type.value,
                    card_id=card.card_id,
                    directed_point=source.key,
                    natal_target=target.key,
                    aspect_type=aspect_name,
                    actual_angle=round(actual_angle, 4),
                    exact_angle=round(exact_angle, 4),
                    orb=round(orb, 4),
                    orb_limit=round(rule.orb_limit, 4),
                    strength=self._strength(orb, rule.orb_limit),
                    formula_rule_matched=rule.id,
                    explanation_for_expert=(
                        f"Directed {source.key} -> Natal {target.key}: {aspect_name}; "
                        f"{ASPECT_MEANINGS.get(aspect_name, 'формульная связь')}."
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
        directed: bool,
        symbolic_arc: float,
    ) -> list[ResolvedPoint]:
        points: list[ResolvedPoint] = []
        for selector in selectors:
            points.extend(
                self._resolve_selector(
                    chart=chart,
                    card=card,
                    selector=selector,
                    directed=directed,
                    symbolic_arc=symbolic_arc,
                )
            )
        return list({point.key: point for point in points}.values())

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
            return [ResolvedPoint(key=f"cusp_{house_num}", degree=self._direct(degree, symbolic_arc, directed))]
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
            if obj.house == house_num:
                points.append(
                    ResolvedPoint(
                        key=f"house_element_{house_num}:{name}",
                        degree=self._direct(obj.absolute_degree_0_360, symbolic_arc, directed),
                    )
                )
        return points

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
        source = rule.display_source or ", ".join(rule.source_selectors) or "source"
        target = rule.display_target or ", ".join(rule.target_selectors) or "target"
        return f"Directed {source} -> Natal {target}"
