from __future__ import annotations

from app.core.constants import ASCMC_LABELS
from app.models.request_models import AspectOrbProfile, ChartRequest
from app.models.response_models import (
    AspectResponse,
    ChartResponse,
    CuspResponse,
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

    cusp_details: dict[str, CuspResponse] = {}
    for house_number, absolute_degree in cusp_values.items():
        sign_index, sign_name, sign_degree = resolve_sign(absolute_degree)
        cusp_details[house_number] = CuspResponse(
            absolute_degree_0_360=absolute_degree,
            sign_index=sign_index,
            sign_name_en=sign_name,
            sign_degree=round(sign_degree, 6),
            sign_degree_dms=degree_to_dms(sign_degree),
        )

    return HousesResponse(system=house_system, cusps=cusp_values, cusp_details=cusp_details)


def _is_degree_in_house_arc(start_degree: float, end_degree: float, value_degree: float) -> bool:
    if start_degree <= end_degree:
        return start_degree <= value_degree < end_degree
    return value_degree >= start_degree or value_degree < end_degree


def assign_object_houses(
    objects: dict[str, ObjectResponse],
    houses: HousesResponse,
) -> dict[str, ObjectResponse]:
    cusp_sequence: list[float] = []
    for index in range(1, 13):
        cusp_value = houses.cusps.get(str(index))
        if not isinstance(cusp_value, (int, float)):
            return objects
        cusp_sequence.append(float(cusp_value))

    assigned: dict[str, ObjectResponse] = {}
    for name, obj in objects.items():
        obj_degree = float(obj.absolute_degree_0_360)
        matched_house: int | None = None
        for house_index in range(12):
            start_degree = cusp_sequence[house_index]
            end_degree = cusp_sequence[(house_index + 1) % 12]
            if _is_degree_in_house_arc(start_degree, end_degree, obj_degree):
                matched_house = house_index + 1
                break

        assigned[name] = obj.model_copy(update={"house": matched_house})

    return assigned


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
    aspect_orb_profile: AspectOrbProfile,
) -> ChartResponse:
    objects_with_houses = assign_object_houses(objects=objects, houses=houses)
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
        objects=objects_with_houses,
        aspects=aspects,
        houses=houses,
        angles=angles,
        meta=MetaResponse(
            zodiac_mode=payload.zodiac_mode,
            sidereal_mode=payload.sidereal_mode,
            object_constants=object_constants,
            aspect_orb_profile=aspect_orb_profile,
            node_definitions={
                "true_node": {
                    "label_ru": "Северный узел истинный",
                    "calculation_type": "true_node",
                },
                "mean_node": {
                    "label_ru": "Северный узел средний",
                    "calculation_type": "mean_node",
                },
            },
        ),
    )
