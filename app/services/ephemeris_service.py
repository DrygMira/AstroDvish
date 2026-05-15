from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from threading import RLock

import swisseph as swe

from app.core.errors import EphemerisCalculationError
from app.models.request_models import ChartRequest, SiderealMode, ZodiacMode
from app.models.response_models import ChartResponse, HousesResponse, ObjectResponse
from app.services.aspects_service import AspectsService
from app.services.formatter_service import (
    augment_node_objects,
    build_angles_payload,
    build_chart_response,
    build_houses_payload,
    build_object_payload,
)

logger = logging.getLogger(__name__)

SWE_CALC_LOCK = RLock()

OBJECT_CONSTANTS: "OrderedDict[str, int]" = OrderedDict(
    [
        ("sun", swe.SUN),
        ("moon", swe.MOON),
        ("mercury", swe.MERCURY),
        ("venus", swe.VENUS),
        ("mars", swe.MARS),
        ("jupiter", swe.JUPITER),
        ("saturn", swe.SATURN),
        ("uranus", swe.URANUS),
        ("neptune", swe.NEPTUNE),
        ("pluto", swe.PLUTO),
        ("true_node", swe.TRUE_NODE),
        ("mean_node", swe.MEAN_NODE),
        ("chiron", swe.CHIRON),
    ]
)

SIDEREAL_MODE_MAP: dict[SiderealMode, int] = {
    SiderealMode.lahiri: swe.SIDM_LAHIRI,
    SiderealMode.fagan_bradley: swe.SIDM_FAGAN_BRADLEY,
    SiderealMode.krishnamurti: swe.SIDM_KRISHNAMURTI,
}


class EphemerisService:
    def __init__(self, ephe_path: str) -> None:
        self.ephe_path = ephe_path
        self.aspects_service = AspectsService()

    def calculate_chart(self, payload: ChartRequest) -> ChartResponse:
        jd_ut = self._to_julian_day_ut(payload.datetime_utc)

        with SWE_CALC_LOCK:
            swe.set_ephe_path(self.ephe_path)
            flags = swe.FLG_SWIEPH | swe.FLG_SPEED
            if payload.zodiac_mode == ZodiacMode.sidereal:
                flags |= swe.FLG_SIDEREAL
                if payload.sidereal_mode is None:
                    raise EphemerisCalculationError(
                        "sidereal_mode is required for sidereal zodiac",
                        details={"zodiac_mode": payload.zodiac_mode.value},
                    )
                sid_mode = SIDEREAL_MODE_MAP[payload.sidereal_mode]
                swe.set_sid_mode(sid_mode)

            objects = self._calculate_objects(jd_ut=jd_ut, flags=flags)
            houses, angles = self._calculate_houses_and_angles(
                jd_ut=jd_ut,
                latitude=payload.latitude,
                longitude=payload.longitude,
                house_system=payload.house_system,
                flags=flags,
            )
            aspect_objects = self._build_aspect_objects(objects)
            aspects = self.aspects_service.calculate_aspects(
                objects=aspect_objects,
                orb_profile=payload.aspect_orb_profile.value,
            )

        return build_chart_response(
            payload=payload,
            julian_day_ut=jd_ut,
            objects=objects,
            aspects=aspects,
            houses=houses,
            angles=angles,
            object_constants={name: int(const) for name, const in OBJECT_CONSTANTS.items()},
            aspect_orb_profile=payload.aspect_orb_profile,
        )

    @staticmethod
    def _to_julian_day_ut(dt: datetime) -> float:
        dt_utc = dt.astimezone(timezone.utc)
        hour_decimal = (
            dt_utc.hour
            + dt_utc.minute / 60
            + dt_utc.second / 3600
            + dt_utc.microsecond / 3_600_000_000
        )
        return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_decimal, swe.GREG_CAL)

    def _calculate_objects(
        self,
        *,
        jd_ut: float,
        flags: int,
    ) -> dict[str, ObjectResponse]:
        result: dict[str, ObjectResponse] = {}
        for name, body in OBJECT_CONSTANTS.items():
            try:
                data, _ = swe.calc_ut(jd_ut, body, flags)
            except swe.Error as exc:
                if name == "chiron":
                    logger.warning("Skipping chiron: %s", exc)
                    continue
                raise EphemerisCalculationError(
                    f"Failed to calculate object {name}",
                    details={"object": name, "error": str(exc)},
                ) from exc
            result[name] = build_object_payload(name, data)
        return result

    @staticmethod
    def _build_aspect_objects(objects: dict[str, ObjectResponse]) -> dict[str, ObjectResponse]:
        augmented = augment_node_objects(objects)
        excluded = {"true_node", "mean_node"}
        return {name: obj for name, obj in augmented.items() if name not in excluded}

    @staticmethod
    def _calculate_houses_and_angles(
        *,
        jd_ut: float,
        latitude: float,
        longitude: float,
        house_system: str,
        flags: int,
    ) -> tuple[HousesResponse, dict[str, float]]:
        try:
            cusps, ascmc = swe.houses_ex(
                jd_ut,
                latitude,
                longitude,
                house_system.encode("ascii"),
                flags,
            )
        except swe.Error as exc:
            raise EphemerisCalculationError(
                "Failed to calculate houses/angles",
                details={"house_system": house_system, "error": str(exc)},
            ) from exc

        houses = build_houses_payload(house_system, cusps)
        angles = build_angles_payload(ascmc)
        return houses, angles
