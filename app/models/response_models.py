from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.request_models import SiderealMode, ZodiacMode


class ObjectResponse(BaseModel):
    name: str
    longitude_deg: float
    latitude_deg: float
    distance_au: float
    speed_longitude_deg_per_day: float
    retrograde: bool
    sign_index: int
    sign_name_en: str
    sign_degree: float
    sign_degree_dms: str
    absolute_degree_0_360: float
    house: int | None = None


class CuspResponse(BaseModel):
    absolute_degree_0_360: float
    sign_index: int
    sign_name_en: str
    sign_degree: float
    sign_degree_dms: str


class InputEchoResponse(BaseModel):
    datetime_utc: str
    latitude: float
    longitude: float
    house_system: str
    zodiac_mode: ZodiacMode
    sidereal_mode: SiderealMode | None


class NormalizedResponse(BaseModel):
    julian_day_ut: float


class HousesResponse(BaseModel):
    system: str
    cusps: dict[str, float]
    cusp_details: dict[str, CuspResponse] = Field(default_factory=dict)


class MetaResponse(BaseModel):
    ephemeris_source: str = "swisseph"
    zodiac_mode: ZodiacMode
    sidereal_mode: SiderealMode | None
    object_constants: dict[str, int] = Field(
        description="Swiss Ephemeris constant mapping for every computed object"
    )
    node_definitions: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Definitions for lunar node calculation types returned in objects"
    )


class AspectResponse(BaseModel):
    object_a: str
    object_b: str
    aspect_type: str
    exact_angle: float
    actual_angle: float
    orb: float
    applying: bool | None = None


class ChartResponse(BaseModel):
    input: InputEchoResponse
    normalized: NormalizedResponse
    objects: dict[str, ObjectResponse]
    aspects: list[AspectResponse] = Field(default_factory=list)
    houses: HousesResponse
    angles: dict[str, float]
    meta: MetaResponse


class ErrorResponse(BaseModel):
    error: dict[str, Any]
