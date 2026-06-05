from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from app.models.rectification_pro_models import RectificationProRunRequest
from app.utils.timezone_lookup import resolve_timezone_name


@dataclass(frozen=True)
class ProTimezoneContext:
    timezone_info: tzinfo
    timezone_name: str
    timezone_offset: str | None
    timezone_source: str
    coordinates_used: dict[str, float]
    payload_path: str = "rectification_direct"


def _format_offset(offset: timedelta | None) -> str | None:
    if offset is None:
        return None
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def _offset_for_date(*, birth_date_local: date, timezone_info: tzinfo) -> str | None:
    if not isinstance(timezone_info, ZoneInfo):
        return None
    offset = datetime.combine(birth_date_local, time.min, timezone_info).utcoffset()
    return _format_offset(offset)


def resolve_pro_timezone_context(
    payload: RectificationProRunRequest,
    *,
    payload_path: str = "rectification_direct",
) -> ProTimezoneContext:
    coordinates_used = {
        "latitude": float(payload.latitude),
        "longitude": float(payload.longitude),
    }
    if payload.timezone_mode == "manual" and payload.timezone_offset:
        sign = 1 if payload.timezone_offset.startswith("+") else -1
        hours = int(payload.timezone_offset[1:3])
        minutes = int(payload.timezone_offset[4:6])
        offset = timedelta(hours=hours, minutes=minutes) * sign
        return ProTimezoneContext(
            timezone_info=timezone(offset),
            timezone_name=f"GMT{payload.timezone_offset}",
            timezone_offset=payload.timezone_offset,
            timezone_source="manual_offset",
            coordinates_used=coordinates_used,
            payload_path=payload_path,
        )

    if payload.timezone_name:
        timezone_info = ZoneInfo(payload.timezone_name)
        return ProTimezoneContext(
            timezone_info=timezone_info,
            timezone_name=payload.timezone_name,
            timezone_offset=_offset_for_date(
                birth_date_local=payload.birth_date_local,
                timezone_info=timezone_info,
            ),
            timezone_source="provided_timezone_name",
            coordinates_used=coordinates_used,
            payload_path=payload_path,
        )

    timezone_name = resolve_timezone_name(
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    timezone_info = ZoneInfo(timezone_name)
    return ProTimezoneContext(
        timezone_info=timezone_info,
        timezone_name=timezone_name,
        timezone_offset=_offset_for_date(
            birth_date_local=payload.birth_date_local,
            timezone_info=timezone_info,
        ),
        timezone_source="resolved_from_coordinates",
        coordinates_used=coordinates_used,
        payload_path=payload_path,
    )


def resolve_pro_timezone(payload: RectificationProRunRequest) -> tuple[tzinfo, str, str | None]:
    context = resolve_pro_timezone_context(payload)
    return context.timezone_info, context.timezone_name, context.timezone_offset
