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
        sign_degree=longitude % 30,
        sign_degree_dms="0°00′00″",
        absolute_degree_0_360=longitude % 360,
    )


def test_aspect_is_calculated_when_within_default_avestan_orb() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "moon": _obj("moon", 7.9),
        }
    )

    assert len(aspects) == 1
    aspect = aspects[0]
    assert aspect.object_a == "Sun"
    assert aspect.object_b == "Moon"
    assert aspect.aspect_type == "conjunction"
    assert aspect.orb == 7.9


def test_avestan_default_is_stricter_for_outer_planets() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "jupiter": _obj("jupiter", 0.0),
            "saturn": _obj("saturn", 6.0),
        }
    )
    assert aspects == []


def test_western_profile_can_be_selected() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "jupiter": _obj("jupiter", 0.0),
            "saturn": _obj("saturn", 6.0),
        },
        orb_profile="western",
    )
    assert len(aspects) == 1
    assert aspects[0].aspect_type == "conjunction"


def test_orb_overrides_are_supported() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "moon": _obj("moon", 8.8),
        },
        orb_overrides={"conjunction": 9.0},
    )
    assert len(aspects) == 1
    assert aspects[0].orb == 8.8


def test_asymmetric_orb_keeps_sun_uranus_conjunction_when_luminary_allows() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "sun": _obj("sun", 0.0),
            "uranus": _obj("uranus", 5.02),
        }
    )

    assert len(aspects) == 1
    assert aspects[0].aspect_type == "conjunction"
    assert aspects[0].orb == 5.02


def test_asymmetric_orb_keeps_moon_neptune_opposition_when_luminary_allows() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "moon": _obj("moon", 0.0),
            "neptune": _obj("neptune", 175.333333),
        }
    )

    assert len(aspects) == 1
    assert aspects[0].aspect_type == "opposition"
    assert aspects[0].orb == 4.666667


def test_asymmetric_orb_keeps_venus_neptune_trine_when_personal_planet_allows() -> None:
    service = AspectsService()
    aspects = service.calculate_aspects(
        objects={
            "venus": _obj("venus", 0.0),
            "neptune": _obj("neptune", 123.1),
        }
    )

    assert len(aspects) == 1
    assert aspects[0].aspect_type == "trine"
    assert aspects[0].orb == 3.1
