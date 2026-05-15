from __future__ import annotations

from dataclasses import dataclass

from app.models.response_models import AspectResponse, ObjectResponse


@dataclass(frozen=True)
class AspectDefinition:
    aspect_type: str
    exact_angle: float


ASPECT_DEFINITIONS: tuple[AspectDefinition, ...] = (
    AspectDefinition("conjunction", 0.0),
    AspectDefinition("opposition", 180.0),
    AspectDefinition("trine", 120.0),
    AspectDefinition("square", 90.0),
    AspectDefinition("sextile", 60.0),
)

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
    "true_north_node": "True North Node",
    "true_south_node": "True South Node",
    "mean_node": "Mean Node",
    "chiron": "Chiron",
}

LUMINARIES = {"sun", "moon"}
PERSONAL_PLANETS = {"mercury", "venus", "mars"}
OUTER_PLANETS = {"jupiter", "saturn", "uranus", "neptune", "pluto"}
SPECIAL_POINTS = {"chiron", "true_node", "true_north_node", "true_south_node", "mean_node"}

DEFAULT_PROFILE = "avestan"

ORB_PROFILE_LIMITS: dict[str, dict[str, float]] = {
    "avestan": {
        "luminary": 7.0,
        "personal": 5.0,
        "outer": 3.0,
        "special": 1.0,
        "fallback": 3.0,
    },
    "western": {
        "luminary": 10.0,
        "personal": 7.0,
        "outer": 7.0,
        "special": 5.0,
        "fallback": 7.0,
    },
}

CONJUNCTION_BONUS_BY_PROFILE: dict[str, float] = {
    "avestan": 1.0,
    "western": 0.0,
}


class AspectsService:
    def calculate_aspects(
        self,
        *,
        objects: dict[str, ObjectResponse],
        orb_profile: str = DEFAULT_PROFILE,
        orb_overrides: dict[str, float] | None = None,
    ) -> list[AspectResponse]:
        if not objects:
            return []

        profile_name = orb_profile if orb_profile in ORB_PROFILE_LIMITS else DEFAULT_PROFILE
        profile_limits = ORB_PROFILE_LIMITS[profile_name]

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

                matched_aspect = self._resolve_aspect(
                    angle=angle,
                    left_name=left_name,
                    right_name=right_name,
                    profile_name=profile_name,
                    profile_limits=profile_limits,
                    orb_overrides=orb_overrides,
                )
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
    def _object_category(name: str) -> str:
        if name in LUMINARIES:
            return "luminary"
        if name in PERSONAL_PLANETS:
            return "personal"
        if name in OUTER_PLANETS:
            return "outer"
        if name in SPECIAL_POINTS:
            return "special"
        return "fallback"

    def _orb_limit_for_pair(
        self,
        *,
        left_name: str,
        right_name: str,
        aspect_type: str,
        profile_name: str,
        profile_limits: dict[str, float],
        orb_overrides: dict[str, float] | None,
    ) -> float:
        if orb_overrides and aspect_type in orb_overrides and orb_overrides[aspect_type] >= 0:
            return float(orb_overrides[aspect_type])

        left_category = self._object_category(left_name)
        right_category = self._object_category(right_name)
        base_limit = max(
            profile_limits.get(left_category, profile_limits["fallback"]),
            profile_limits.get(right_category, profile_limits["fallback"]),
        )

        if aspect_type == "conjunction":
            base_limit += CONJUNCTION_BONUS_BY_PROFILE.get(profile_name, 0.0)

        return base_limit

    def _resolve_aspect(
        self,
        *,
        angle: float,
        left_name: str,
        right_name: str,
        profile_name: str,
        profile_limits: dict[str, float],
        orb_overrides: dict[str, float] | None,
    ) -> tuple[AspectDefinition, float] | None:
        best_match: tuple[AspectDefinition, float] | None = None
        for aspect in ASPECT_DEFINITIONS:
            orb_limit = self._orb_limit_for_pair(
                left_name=left_name,
                right_name=right_name,
                aspect_type=aspect.aspect_type,
                profile_name=profile_name,
                profile_limits=profile_limits,
                orb_overrides=orb_overrides,
            )
            orb = abs(angle - aspect.exact_angle)
            if orb > orb_limit:
                continue
            if best_match is None or orb < best_match[1]:
                best_match = (aspect, orb)
        return best_match
