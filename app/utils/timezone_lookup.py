from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from timezonefinder import TimezoneFinder

from app.core.errors import TimezoneLookupError

_timezone_finder = TimezoneFinder(in_memory=True)


def resolve_timezone_name(*, latitude: float, longitude: float) -> str:
    timezone_name = _timezone_finder.timezone_at(lng=longitude, lat=latitude)

    if timezone_name is None:
        raise TimezoneLookupError(
            "Could not determine timezone for coordinates",
            details={"latitude": latitude, "longitude": longitude},
        )

    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise TimezoneLookupError(
            "Invalid timezone name returned for coordinates",
            details={
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone_name,
            },
        ) from exc

    return timezone_name
