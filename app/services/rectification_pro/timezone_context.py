from __future__ import annotations

from datetime import timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from app.models.rectification_pro_models import RectificationProRunRequest
from app.utils.timezone_lookup import resolve_timezone_name


def resolve_pro_timezone(payload: RectificationProRunRequest) -> tuple[tzinfo, str, str | None]:
    if payload.timezone_mode == "manual" and payload.timezone_offset:
        sign = 1 if payload.timezone_offset.startswith("+") else -1
        hours = int(payload.timezone_offset[1:3])
        minutes = int(payload.timezone_offset[4:6])
        offset = timedelta(hours=hours, minutes=minutes) * sign
        return timezone(offset), f"GMT{payload.timezone_offset}", payload.timezone_offset
    timezone_name = payload.timezone_name or resolve_timezone_name(
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    return ZoneInfo(timezone_name), timezone_name, None
