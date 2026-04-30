from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import SUPPORTED_HOUSE_SYSTEMS
from app.models.request_models import SiderealMode, ZodiacMode


class AscSignIntervalsRequest(BaseModel):
    birth_date_local: date
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    house_system: str = Field(default="P", min_length=1, max_length=1)
    zodiac_mode: ZodiacMode = ZodiacMode.tropical
    sidereal_mode: SiderealMode | None = None

    @field_validator("house_system")
    @classmethod
    def _validate_house_system(cls, value: str) -> str:
        upper_value = value.upper()
        if upper_value not in SUPPORTED_HOUSE_SYSTEMS:
            allowed = ", ".join(sorted(SUPPORTED_HOUSE_SYSTEMS))
            raise ValueError(f"Unsupported house_system. Supported values: {allowed}")
        return upper_value

    @model_validator(mode="after")
    def _validate_zodiac_combination(self) -> "AscSignIntervalsRequest":
        if self.zodiac_mode == ZodiacMode.tropical and self.sidereal_mode is not None:
            raise ValueError("sidereal_mode must be null when zodiac_mode is tropical")

        if self.zodiac_mode == ZodiacMode.sidereal and self.sidereal_mode is None:
            raise ValueError("sidereal_mode is required when zodiac_mode is sidereal")

        return self


class BirthContextResponse(BaseModel):
    birth_date_local: str
    latitude: float
    longitude: float
    timezone: str
    timezone_source: str
    house_system: str
    zodiac_mode: ZodiacMode
    sidereal_mode: SiderealMode | None


class DayWindowResponse(BaseModel):
    start_local: str
    end_local: str


class DayWindowUtcResponse(BaseModel):
    start_utc: str
    end_utc: str


class SharedDaySummaryResponse(BaseModel):
    sun_sign: str
    moon_sign_start: str
    moon_sign_end: str
    moon_changes_sign_today: bool
    mercury_sign: str
    venus_sign: str
    mars_sign: str
    jupiter_sign: str
    saturn_sign: str


class SamplePointResponse(BaseModel):
    local_time: str
    asc_degree_in_sign: float
    moon_sign: str
    mc_sign: str


class IntervalSamplePointsResponse(BaseModel):
    p15: SamplePointResponse
    p50: SamplePointResponse
    p85: SamplePointResponse


class AscSignIntervalResponse(BaseModel):
    interval_index: int
    sign_index: int
    sign_name_en: str
    sign_name_ru: str
    start_local: str
    end_local: str
    duration_minutes: int
    sample_points: IntervalSamplePointsResponse
    changing_features_within_interval: list[str]


class AscSignIntervalsResponse(BaseModel):
    mode: str
    version: str
    generated_at_utc: str
    birth_context: BirthContextResponse
    day_window: DayWindowResponse
    day_window_utc: DayWindowUtcResponse
    shared_day_summary: SharedDaySummaryResponse
    asc_sign_intervals: list[AscSignIntervalResponse]
