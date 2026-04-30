from __future__ import annotations

from app.models.response_models import ObjectResponse
from app.services.aspects_service import AspectsService


def _obj(name: str, longitude: float) -> ObjectResponse:
    return ObjectResponse(
        name=name,
        longitude_deg=longitude,
        latitude_deg=0.0,
        distance_au=1.0,
        speed_longitude_deg_per_day=1.0,
        retrograde=False,
        sign_index=0,
        sign_name_en="Aries",
        sign_degree=longitude,
        sign_degree_dms="0°0'0\"",
        absolute_degree_0_360=longitude,
    )


def test_aspect_is_calculated_when_within_orb() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "moon": _obj("moon", 118.4),
        }
    )

    assert len(aspects) == 1
    aspect = aspects[0]
    assert aspect.object_a == "Sun"
    assert aspect.object_b == "Moon"
    assert aspect.aspect_type == "trine"
    assert aspect.exact_angle == 120.0
    assert aspect.actual_angle == 118.4
    assert aspect.orb == 1.6
    assert aspect.applying is None


def test_aspect_is_not_calculated_outside_orb() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "moon": _obj("moon", 52.0),
        }
    )
    assert aspects == []


def test_aspects_have_no_duplicates_or_self_relations() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "moon": _obj("moon", 60.0),
            "mars": _obj("mars", 120.0),
        }
    )

    pairs = {(aspect.object_a, aspect.object_b) for aspect in aspects}
    assert len(pairs) == len(aspects)
    assert ("Sun", "Sun") not in pairs
    assert ("Moon", "Moon") not in pairs
    assert ("Mars", "Mars") not in pairs
    assert ("Moon", "Sun") not in pairs


def test_orb_is_calculated_correctly() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "moon": _obj("moon", 92.25),
        }
    )

    assert len(aspects) == 1
    aspect = aspects[0]
    assert aspect.aspect_type == "square"
    assert aspect.exact_angle == 90.0
    assert aspect.actual_angle == 92.25
    assert aspect.orb == 2.25


def test_orbs_are_configurable_with_overrides() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "moon": _obj("moon", 63.0),
        },
        orb_overrides={"sextile": 2.0},
    )
    assert aspects == []
