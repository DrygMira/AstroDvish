from __future__ import annotations

from app.core.constants import ASCMC_LABELS
from app.models.request_models import ChartRequest
from app.models.response_models import (
    AspectResponse,
    ChartResponse,
    HousesResponse,
    InputEchoResponse,
    MetaResponse,
    NormalizedResponse,
    ObjectResponse,
)
from app.services.zodiac_service import degree_to_dms, normalize_degree, resolve_sign


def build_object_payload(name: str, raw_values: tuple[float, ...]) -> ObjectResponse:
    longitude = normalize_degree(raw_values[0])
    latitude = raw_values[1]
    distance = raw_values[2]
    speed_longitude = raw_values[3]

    sign_index, sign_name, sign_degree = resolve_sign(longitude)
    return ObjectResponse(
        name=name,
        longitude_deg=round(longitude, 6),
        latitude_deg=round(latitude, 6),
        distance_au=round(distance, 9),
        speed_longitude_deg_per_day=round(speed_longitude, 6),
        retrograde=speed_longitude < 0,
        sign_index=sign_index,
        sign_name_en=sign_name,
        sign_degree=round(sign_degree, 6),
        sign_degree_dms=degree_to_dms(sign_degree),
        absolute_degree_0_360=round(longitude, 6),
    )


def build_houses_payload(house_system: str, cusps: tuple[float, ...]) -> HousesResponse:
    if len(cusps) >= 13:
        cusp_values = {str(i): round(normalize_degree(cusps[i]), 6) for i in range(1, 13)}
    else:
        cusp_values = {
            str(i + 1): round(normalize_degree(cusps[i]), 6) for i in range(min(len(cusps), 12))
        }

    return HousesResponse(
        system=house_system,
        cusps=cusp_values,
    )


def build_angles_payload(ascmc: tuple[float, ...]) -> dict[str, float]:
    angles: dict[str, float] = {}
    for idx, label in ASCMC_LABELS.items():
        if idx < len(ascmc):
            angles[label] = round(normalize_degree(ascmc[idx]), 6)
    return angles


def build_chart_response(
    payload: ChartRequest,
    julian_day_ut: float,
    objects: dict[str, ObjectResponse],
    aspects: list[AspectResponse],
    houses: HousesResponse,
    angles: dict[str, float],
    object_constants: dict[str, int],
) -> ChartResponse:
    return ChartResponse(
        input=InputEchoResponse(
            datetime_utc=payload.datetime_as_z(),
            latitude=payload.latitude,
            longitude=payload.longitude,
            house_system=payload.house_system,
            zodiac_mode=payload.zodiac_mode,
            sidereal_mode=payload.sidereal_mode,
        ),
        normalized=NormalizedResponse(julian_day_ut=round(julian_day_ut, 9)),
        objects=objects,
        aspects=aspects,
        houses=houses,
        angles=angles,
        meta=MetaResponse(
            zodiac_mode=payload.zodiac_mode,
            sidereal_mode=payload.sidereal_mode,
            object_constants=object_constants,
        ),
    )
