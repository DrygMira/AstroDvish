from __future__ import annotations

from dataclasses import dataclass

from app.models.response_models import AspectResponse, ObjectResponse


@dataclass(frozen=True)
class AspectDefinition:
    aspect_type: str
    exact_angle: float
    default_orb: float


ASPECT_DEFINITIONS: tuple[AspectDefinition, ...] = (
    AspectDefinition("conjunction", 0.0, 8.0),
    AspectDefinition("opposition", 180.0, 8.0),
    AspectDefinition("trine", 120.0, 7.0),
    AspectDefinition("square", 90.0, 6.0),
    AspectDefinition("sextile", 60.0, 5.0),
)

DEFAULT_ASPECT_ORBS: dict[str, float] = {
    definition.aspect_type: definition.default_orb for definition in ASPECT_DEFINITIONS
}

OBJECT_DISPLAY_NAMES: dict[str, str] = {
    "sun": "Sun",
    "moon": "Moon",
    "mercury": "Mercury",
    "venus": "Venus",
    "mars": "Mars",
    "jupiter": "Jupiter",
    "saturn": "Saturn",
    "uranus": "Uranus",
    "neptune": "Neptune",
    "pluto": "Pluto",
    "true_node": "True Node",
    "mean_node": "Mean Node",
    "chiron": "Chiron",
}


class AspectsService:
    def __init__(self, default_orbs: dict[str, float] | None = None) -> None:
        self.default_orbs = dict(default_orbs or DEFAULT_ASPECT_ORBS)

    def calculate_aspects(
        self,
        *,
        objects: dict[str, ObjectResponse],
        orb_overrides: dict[str, float] | None = None,
    ) -> list[AspectResponse]:
        if not objects:
            return []

        effective_orbs = dict(self.default_orbs)
        if orb_overrides:
            for aspect_type, orb_value in orb_overrides.items():
                if aspect_type not in effective_orbs:
                    continue
                if orb_value < 0:
                    continue
                effective_orbs[aspect_type] = orb_value

        object_names = list(objects.keys())
        result: list[AspectResponse] = []
        for i in range(len(object_names)):
            for j in range(i + 1, len(object_names)):
                left_name = object_names[i]
                right_name = object_names[j]
                left_obj = objects[left_name]
                right_obj = objects[right_name]

                angle = self._minimal_angular_distance(
                    left_obj.absolute_degree_0_360,
                    right_obj.absolute_degree_0_360,
                )

                matched_aspect = self._resolve_aspect(angle=angle, effective_orbs=effective_orbs)
                if matched_aspect is None:
                    continue

                aspect_definition, orb = matched_aspect
                result.append(
                    AspectResponse(
                        object_a=OBJECT_DISPLAY_NAMES.get(left_name, left_obj.name.title()),
                        object_b=OBJECT_DISPLAY_NAMES.get(right_name, right_obj.name.title()),
                        aspect_type=aspect_definition.aspect_type,
                        exact_angle=round(aspect_definition.exact_angle, 6),
                        actual_angle=round(angle, 6),
                        orb=round(orb, 6),
                        applying=None,
                    )
                )

        return result

    @staticmethod
    def _minimal_angular_distance(left: float, right: float) -> float:
        delta = abs(left - right) % 360
        return delta if delta <= 180 else 360 - delta

    @staticmethod
    def _resolve_aspect(
        *,
        angle: float,
        effective_orbs: dict[str, float],
    ) -> tuple[AspectDefinition, float] | None:
        best_match: tuple[AspectDefinition, float] | None = None
        for aspect in ASPECT_DEFINITIONS:
            orb_limit = effective_orbs.get(aspect.aspect_type, aspect.default_orb)
            orb = abs(angle - aspect.exact_angle)
            if orb > orb_limit:
                continue
            if best_match is None or orb < best_match[1]:
                best_match = (aspect, orb)
        return best_match

