from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from app.models.event_models import DatePrecision, EventCard
from app.models.request_models import ChartRequest
from app.models.response_models import ChartResponse
from app.services.ephemeris_service import EphemerisService

DirectionMethod = Literal["symbolic_1deg_per_year", "solar_arc"]


@dataclass(frozen=True)
class DirectionChartBuildResult:
    direction_method: DirectionMethod
    direction_arc: float
    event_date: date
    event_datetime_used: str
    candidate_birth_datetime_local: str | None
    candidate_birth_datetime_utc: str | None
    timezone_used: str | None
    natal_points: dict[str, float]
    directed_points: dict[str, float]

    def natal_coordinate(self, point_key: str) -> float | None:
        return self.natal_points.get(point_key)

    def directed_coordinate(self, point_key: str) -> float | None:
        return self.directed_points.get(point_key)


class DirectionChartBuilder:
    def __init__(
        self,
        *,
        ephemeris_service: EphemerisService | None = None,
        default_method: DirectionMethod = "symbolic_1deg_per_year",
    ) -> None:
        self.ephemeris_service = ephemeris_service
        self.default_method = default_method

    def build(
        self,
        *,
        natal_chart: ChartResponse,
        candidate_birth_date: date,
        candidate_birth_datetime_local: str | None = None,
        candidate_birth_datetime_utc: str | None = None,
        timezone_used: str | None = None,
        timezone_offset_used: str | None = None,
        event: EventCard,
        direction_method: DirectionMethod | None = None,
    ) -> DirectionChartBuildResult:
        event_date = self._event_anchor_date(event)
        if event_date is None:
            raise ValueError("event_date_unknown_for_directions")

        birth_local_dt, birth_utc_dt = self._resolve_birth_datetimes(
            candidate_birth_date=candidate_birth_date,
            candidate_birth_datetime_local=candidate_birth_datetime_local,
            candidate_birth_datetime_utc=candidate_birth_datetime_utc,
            timezone_used=timezone_used,
            timezone_offset_used=timezone_offset_used,
        )
        event_anchor_dt = datetime.combine(event_date, time(0, 0, 0), tzinfo=birth_local_dt.tzinfo)
        age_years = self._age_in_tropical_years(birth_local_dt, event_anchor_dt)
        if age_years < 0:
            raise ValueError("event_before_birth_date")

        method: DirectionMethod = direction_method or self.default_method
        if method == "symbolic_1deg_per_year":
            direction_arc = age_years % 360.0
        elif method == "solar_arc":
            direction_arc = self._solar_arc(
                natal_chart=natal_chart,
                age_years=age_years,
            )
        else:
            raise ValueError(f"unsupported_direction_method={method}")

        natal_points = self._collect_natal_points(natal_chart)
        directed_points = {
            point_key: (degree + direction_arc) % 360.0
            for point_key, degree in natal_points.items()
        }
        return DirectionChartBuildResult(
            direction_method=method,
            direction_arc=round(direction_arc, 6),
            event_date=event_date,
            event_datetime_used=event_anchor_dt.isoformat(timespec="seconds"),
            candidate_birth_datetime_local=birth_local_dt.isoformat(timespec="seconds"),
            candidate_birth_datetime_utc=birth_utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            timezone_used=timezone_used,
            natal_points=natal_points,
            directed_points=directed_points,
        )

    @staticmethod
    def _event_anchor_date(event: EventCard) -> date | None:
        if event.start_date:
            return date.fromisoformat(event.start_date)
        if event.date_precision == DatePrecision.exact and event.date_text:
            try:
                return date.fromisoformat(event.date_text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _age_in_tropical_years(candidate_birth_datetime: datetime, event_datetime: datetime) -> float:
        return (event_datetime - candidate_birth_datetime).total_seconds() / 86400.0 / 365.2425

    def _solar_arc(
        self,
        *,
        natal_chart: ChartResponse,
        age_years: float,
    ) -> float:
        if self.ephemeris_service is None:
            raise ValueError("solar_arc_requires_ephemeris_service")

        natal_sun = natal_chart.objects.get("sun")
        if natal_sun is None:
            raise ValueError("solar_arc_requires_natal_sun")

        natal_datetime = self._parse_chart_datetime(natal_chart.input.datetime_utc)
        progressed_datetime = natal_datetime + timedelta(days=age_years)
        progressed_request = ChartRequest(
            datetime_utc=progressed_datetime.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            latitude=natal_chart.input.latitude,
            longitude=natal_chart.input.longitude,
            house_system=natal_chart.input.house_system,
            zodiac_mode=natal_chart.input.zodiac_mode,
            sidereal_mode=natal_chart.input.sidereal_mode,
            aspect_orb_profile=natal_chart.meta.aspect_orb_profile,
        )
        progressed_chart = self.ephemeris_service.calculate_chart(progressed_request)
        progressed_sun = progressed_chart.objects.get("sun")
        if progressed_sun is None:
            raise ValueError("solar_arc_requires_progressed_sun")

        return (progressed_sun.absolute_degree_0_360 - natal_sun.absolute_degree_0_360) % 360.0

    @staticmethod
    def _parse_chart_datetime(raw: str) -> datetime:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _resolve_birth_datetimes(
        cls,
        *,
        candidate_birth_date: date,
        candidate_birth_datetime_local: str | None,
        candidate_birth_datetime_utc: str | None,
        timezone_used: str | None,
        timezone_offset_used: str | None,
    ) -> tuple[datetime, datetime]:
        tzinfo = cls._timezone_info(timezone_used=timezone_used, timezone_offset_used=timezone_offset_used)
        if candidate_birth_datetime_local:
            local_dt = cls._parse_local_datetime(candidate_birth_datetime_local, tzinfo)
            return local_dt, local_dt.astimezone(timezone.utc)
        if candidate_birth_datetime_utc:
            utc_dt = cls._parse_chart_datetime(candidate_birth_datetime_utc)
            return utc_dt.astimezone(tzinfo), utc_dt
        local_dt = datetime.combine(candidate_birth_date, time(0, 0, 0), tzinfo=tzinfo)
        return local_dt, local_dt.astimezone(timezone.utc)

    @staticmethod
    def _parse_local_datetime(raw: str, tzinfo) -> datetime:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tzinfo)
        return parsed.astimezone(tzinfo)

    @staticmethod
    def _timezone_info(*, timezone_used: str | None, timezone_offset_used: str | None):
        if timezone_offset_used:
            sign = 1 if timezone_offset_used.startswith("+") else -1
            hours = int(timezone_offset_used[1:3])
            minutes = int(timezone_offset_used[4:6])
            return timezone(sign * timedelta(hours=hours, minutes=minutes))
        if timezone_used and timezone_used.startswith("GMT") and len(timezone_used) >= 9:
            offset = timezone_used[3:]
            sign = 1 if offset.startswith("+") else -1
            hours = int(offset[1:3])
            minutes = int(offset[4:6])
            return timezone(sign * timedelta(hours=hours, minutes=minutes))
        if timezone_used:
            return ZoneInfo(timezone_used)
        return timezone.utc

    @staticmethod
    def _collect_natal_points(chart: ChartResponse) -> dict[str, float]:
        points: dict[str, float] = {
            name: float(obj.absolute_degree_0_360)
            for name, obj in chart.objects.items()
            if name != "gradarch"
        }
        for house_num, cusp in chart.houses.cusps.items():
            points[f"cusp_{house_num}"] = float(cusp)
        if "asc" in chart.angles:
            points["asc"] = float(chart.angles["asc"])
            points["desc"] = (float(chart.angles["asc"]) + 180.0) % 360.0
        if "mc" in chart.angles:
            points["mc"] = float(chart.angles["mc"])
            points["ic"] = (float(chart.angles["mc"]) + 180.0) % 360.0
        return points
