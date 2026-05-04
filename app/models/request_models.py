from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import SUPPORTED_HOUSE_SYSTEMS


class ZodiacMode(str, Enum):
    tropical = "tropical"
    sidereal = "sidereal"


class SiderealMode(str, Enum):
    lahiri = "lahiri"
    fagan_bradley = "fagan_bradley"
    krishnamurti = "krishnamurti"


class AspectOrbProfile(str, Enum):
    avestan = "avestan"
    western = "western"


class ChartRequest(BaseModel):
    datetime_utc: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    house_system: str = Field(default="P", min_length=1, max_length=1)
    zodiac_mode: ZodiacMode = ZodiacMode.tropical
    sidereal_mode: SiderealMode | None = None
    aspect_orb_profile: AspectOrbProfile = AspectOrbProfile.avestan

    @field_validator("datetime_utc", mode="before")
    @classmethod
    def _validate_datetime_utc(cls, value: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError("datetime_utc must be an ISO 8601 UTC string")

        raw = value.strip()
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                "datetime_utc must be valid ISO 8601 UTC (example: 1984-11-13T11:35:00Z)"
            ) from exc

        if parsed.tzinfo is None:
            raise ValueError("datetime_utc must include UTC timezone")
        if parsed.utcoffset() != timedelta(0):
            raise ValueError("datetime_utc must be in UTC")

        return parsed.astimezone(timezone.utc)

    @field_validator("house_system")
    @classmethod
    def _validate_house_system(cls, value: str) -> str:
        upper_value = value.upper()
        if upper_value not in SUPPORTED_HOUSE_SYSTEMS:
            allowed = ", ".join(sorted(SUPPORTED_HOUSE_SYSTEMS))
            raise ValueError(f"Unsupported house_system. Supported values: {allowed}")
        return upper_value

    @model_validator(mode="after")
    def _validate_zodiac_combination(self) -> ChartRequest:
        if self.zodiac_mode == ZodiacMode.tropical and self.sidereal_mode is not None:
            raise ValueError("sidereal_mode must be null when zodiac_mode is tropical")

        if self.zodiac_mode == ZodiacMode.sidereal and self.sidereal_mode is None:
            raise ValueError(
                "sidereal_mode is required when zodiac_mode is sidereal"
            )

        return self

    def datetime_as_z(self) -> str:
        return self.datetime_utc.isoformat().replace("+00:00", "Z")

