from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

from app.core.constants import ZODIAC_SIGN_NAMES_EN, ZODIAC_SIGN_NAMES_RU
from app.core.errors import RectificationCalculationError
from app.models.rectification_models import (
    AscSignIntervalResponse,
    AscSignIntervalsRequest,
    AscSignIntervalsResponse,
    BirthContextResponse,
    DayWindowResponse,
    IntervalSamplePointsResponse,
    SamplePointResponse,
    SharedDaySummaryResponse,
)
from app.models.request_models import ZodiacMode
from app.services.ephemeris_service import SIDEREAL_MODE_MAP, SWE_CALC_LOCK
from app.services.zodiac_service import normalize_degree, resolve_sign
from app.utils import timezone_lookup


@dataclass(frozen=True)
class _PointSnapshot:
    asc_sign_index: int
    asc_degree_in_sign: float
    moon_sign: str
    mc_sign: str


class AscSignIntervalsService:
    def __init__(self, ephe_path: str) -> None:
        self.ephe_path = ephe_path

    def calculate_intervals(self, payload: AscSignIntervalsRequest) -> AscSignIntervalsResponse:
        timezone_name = timezone_lookup.resolve_timezone_name(
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        timezone_info = ZoneInfo(timezone_name)
        start_local = datetime.combine(payload.birth_date_local, time.min, timezone_info)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        intervals_start_utc, intervals_end_utc = self._expand_day_bounds_to_full_sign_intervals(
            start_utc=start_utc,
            end_utc=end_utc,
            payload=payload,
        )

        shared_summary = self._build_shared_day_summary(
            start_utc=start_utc,
            end_utc=end_utc,
            payload=payload,
        )
        asc_intervals = self._build_asc_intervals(
            start_utc=intervals_start_utc,
            end_utc=intervals_end_utc,
            timezone_info=timezone_info,
            payload=payload,
        )

        return AscSignIntervalsResponse(
            mode="asc_sign_intervals",
            version="1.0",
            generated_at_utc=self._to_utc_z(datetime.now(timezone.utc)),
            birth_context=BirthContextResponse(
                birth_date_local=payload.birth_date_local.isoformat(),
                latitude=payload.latitude,
                longitude=payload.longitude,
                timezone=timezone_name,
                house_system=payload.house_system,
                zodiac_mode=payload.zodiac_mode,
                sidereal_mode=payload.sidereal_mode,
            ),
            day_window=DayWindowResponse(
                start_local=self._to_local_iso(start_local),
                end_local=self._to_local_iso(end_local),
            ),
            shared_day_summary=shared_summary,
            asc_sign_intervals=asc_intervals,
        )

    def _expand_day_bounds_to_full_sign_intervals(
        self,
        *,
        start_utc: datetime,
        end_utc: datetime,
        payload: AscSignIntervalsRequest,
    ) -> tuple[datetime, datetime]:
        if end_utc <= start_utc:
            return start_utc, end_utc

        start_sign = self._calculate_asc_sign_index(start_utc, payload)
        end_probe_utc = max(start_utc, end_utc - timedelta(seconds=1))
        end_sign = self._calculate_asc_sign_index(end_probe_utc, payload)

        full_start = self._find_previous_sign_change_boundary(
            reference_time_utc=start_utc,
            current_sign=start_sign,
            payload=payload,
        )
        full_end = self._find_next_sign_change_boundary(
            reference_time_utc=end_probe_utc,
            current_sign=end_sign,
            payload=payload,
        )

        if full_start >= start_utc:
            full_start = start_utc
        if full_end <= end_utc:
            full_end = end_utc

        return full_start, full_end

    def _find_previous_sign_change_boundary(
        self,
        *,
        reference_time_utc: datetime,
        current_sign: int,
        payload: AscSignIntervalsRequest,
    ) -> datetime:
        step = timedelta(minutes=5)
        lookback_limit = timedelta(days=2)
        walked = timedelta(0)
        right = reference_time_utc
        left = right - step

        while walked <= lookback_limit:
            left_sign = self._calculate_asc_sign_index(left, payload)
            if left_sign != current_sign:
                boundary = self._refine_sign_boundary(
                    left=left,
                    right=right,
                    from_sign=left_sign,
                    payload=payload,
                )
                return boundary
            right = left
            left = left - step
            walked += step

        raise RectificationCalculationError(
            "Failed to locate previous asc sign boundary",
            details={
                "reference_time_utc": self._to_utc_z(reference_time_utc),
                "current_sign": current_sign,
            },
        )

    def _find_next_sign_change_boundary(
        self,
        *,
        reference_time_utc: datetime,
        current_sign: int,
        payload: AscSignIntervalsRequest,
    ) -> datetime:
        step = timedelta(minutes=5)
        lookahead_limit = timedelta(days=2)
        walked = timedelta(0)
        left = reference_time_utc
        right = left + step

        while walked <= lookahead_limit:
            right_sign = self._calculate_asc_sign_index(right, payload)
            if right_sign != current_sign:
                boundary = self._refine_sign_boundary(
                    left=left,
                    right=right,
                    from_sign=current_sign,
                    payload=payload,
                )
                return boundary
            left = right
            right = right + step
            walked += step

        raise RectificationCalculationError(
            "Failed to locate next asc sign boundary",
            details={
                "reference_time_utc": self._to_utc_z(reference_time_utc),
                "current_sign": current_sign,
            },
        )

    def _build_shared_day_summary(
        self,
        *,
        start_utc: datetime,
        end_utc: datetime,
        payload: AscSignIntervalsRequest,
    ) -> SharedDaySummaryResponse:
        end_probe_utc = max(start_utc, end_utc - timedelta(seconds=1))
        moon_sign_start = self._calculate_object_sign(start_utc, swe.MOON, payload)
        moon_sign_end = self._calculate_object_sign(end_probe_utc, swe.MOON, payload)
        return SharedDaySummaryResponse(
            sun_sign=self._calculate_object_sign(start_utc, swe.SUN, payload),
            moon_sign_start=moon_sign_start,
            moon_sign_end=moon_sign_end,
            moon_changes_sign_today=moon_sign_start != moon_sign_end,
            mercury_sign=self._calculate_object_sign(start_utc, swe.MERCURY, payload),
            venus_sign=self._calculate_object_sign(start_utc, swe.VENUS, payload),
            mars_sign=self._calculate_object_sign(start_utc, swe.MARS, payload),
            jupiter_sign=self._calculate_object_sign(start_utc, swe.JUPITER, payload),
            saturn_sign=self._calculate_object_sign(start_utc, swe.SATURN, payload),
        )

    def _build_asc_intervals(
        self,
        *,
        start_utc: datetime,
        end_utc: datetime,
        timezone_info: ZoneInfo,
        payload: AscSignIntervalsRequest,
    ) -> list[AscSignIntervalResponse]:
        if start_utc >= end_utc:
            return []

        intervals_raw: list[tuple[datetime, datetime, int]] = []
        step = timedelta(minutes=5)
        scan_time = start_utc
        interval_start = start_utc
        current_sign = self._calculate_asc_sign_index(scan_time, payload)

        while scan_time < end_utc:
            next_scan_time = min(scan_time + step, end_utc)
            next_sign = self._calculate_asc_sign_index(next_scan_time, payload)
            if next_sign == current_sign:
                scan_time = next_scan_time
                continue

            boundary = self._refine_sign_boundary(
                left=scan_time,
                right=next_scan_time,
                from_sign=current_sign,
                payload=payload,
            )
            if boundary <= interval_start:
                boundary = min(interval_start + timedelta(minutes=1), end_utc)

            intervals_raw.append((interval_start, boundary, current_sign))
            interval_start = boundary
            scan_time = boundary
            current_sign = self._calculate_asc_sign_index(scan_time, payload)

        if interval_start < end_utc:
            intervals_raw.append((interval_start, end_utc, current_sign))

        result: list[AscSignIntervalResponse] = []
        for index, (interval_start_utc, interval_end_utc, sign_index) in enumerate(
            intervals_raw, start=1
        ):
            result.append(
                self._build_single_interval(
                    interval_index=index,
                    sign_index=sign_index,
                    start_utc=interval_start_utc,
                    end_utc=interval_end_utc,
                    timezone_info=timezone_info,
                    payload=payload,
                )
            )

        return result

    def _build_single_interval(
        self,
        *,
        interval_index: int,
        sign_index: int,
        start_utc: datetime,
        end_utc: datetime,
        timezone_info: ZoneInfo,
        payload: AscSignIntervalsRequest,
    ) -> AscSignIntervalResponse:
        if end_utc < start_utc:
            raise RectificationCalculationError(
                "Asc interval end is earlier than start",
                details={"start_utc": self._to_utc_z(start_utc), "end_utc": self._to_utc_z(end_utc)},
            )

        interval_seconds = (end_utc - start_utc).total_seconds()
        duration_minutes = 0
        if interval_seconds > 0:
            duration_minutes = max(1, int((interval_seconds + 30) // 60))

        p15_utc = self._interpolate_time(start_utc, end_utc, ratio=0.15)
        p50_utc = self._interpolate_time(start_utc, end_utc, ratio=0.50)
        p85_utc = self._interpolate_time(start_utc, end_utc, ratio=0.85)

        p15 = self._build_sample_point(p15_utc, timezone_info, payload)
        p50 = self._build_sample_point(p50_utc, timezone_info, payload)
        p85 = self._build_sample_point(p85_utc, timezone_info, payload)

        start_snapshot = self._calculate_point_snapshot(start_utc, payload)
        end_probe_utc = max(start_utc, end_utc - timedelta(seconds=1))
        end_snapshot = self._calculate_point_snapshot(end_probe_utc, payload)

        changing_features: list[str] = []
        if start_snapshot.mc_sign != end_snapshot.mc_sign:
            changing_features.append(
                f"mc_sign_changes_{start_snapshot.mc_sign.lower()}_to_{end_snapshot.mc_sign.lower()}"
            )

        return AscSignIntervalResponse(
            interval_index=interval_index,
            sign_index=sign_index,
            sign_name_en=ZODIAC_SIGN_NAMES_EN[sign_index],
            sign_name_ru=ZODIAC_SIGN_NAMES_RU[sign_index],
            start_local=self._to_local_iso(start_utc.astimezone(timezone_info)),
            end_local=self._to_local_iso(end_utc.astimezone(timezone_info)),
            duration_minutes=duration_minutes,
            sample_points=IntervalSamplePointsResponse(p15=p15, p50=p50, p85=p85),
            changing_features_within_interval=changing_features,
        )

    def _build_sample_point(
        self,
        dt_utc: datetime,
        timezone_info: ZoneInfo,
        payload: AscSignIntervalsRequest,
    ) -> SamplePointResponse:
        snapshot = self._calculate_point_snapshot(dt_utc, payload)
        return SamplePointResponse(
            local_time=self._to_local_iso(dt_utc.astimezone(timezone_info)),
            asc_degree_in_sign=round(snapshot.asc_degree_in_sign, 6),
            moon_sign=snapshot.moon_sign,
            mc_sign=snapshot.mc_sign,
        )

    def _calculate_point_snapshot(
        self,
        dt_utc: datetime,
        payload: AscSignIntervalsRequest,
    ) -> _PointSnapshot:
        jd_ut = self._to_julian_day_ut(dt_utc)
        with SWE_CALC_LOCK:
            flags = self._prepare_swe(payload)
            try:
                _, ascmc = swe.houses_ex(
                    jd_ut,
                    payload.latitude,
                    payload.longitude,
                    payload.house_system.encode("ascii"),
                    flags,
                )
                moon_data, _ = swe.calc_ut(jd_ut, swe.MOON, flags)
            except swe.Error as exc:
                raise RectificationCalculationError(
                    "Failed to calculate sample snapshot",
                    details={"error": str(exc)},
                ) from exc

        asc_index, _, asc_degree = resolve_sign(normalize_degree(ascmc[0]))
        _, moon_sign, _ = resolve_sign(normalize_degree(moon_data[0]))
        _, mc_sign, _ = resolve_sign(normalize_degree(ascmc[1]))
        return _PointSnapshot(
            asc_sign_index=asc_index,
            asc_degree_in_sign=asc_degree,
            moon_sign=moon_sign,
            mc_sign=mc_sign,
        )

    def _calculate_asc_sign_index(self, dt_utc: datetime, payload: AscSignIntervalsRequest) -> int:
        jd_ut = self._to_julian_day_ut(dt_utc)
        with SWE_CALC_LOCK:
            flags = self._prepare_swe(payload)
            try:
                _, ascmc = swe.houses_ex(
                    jd_ut,
                    payload.latitude,
                    payload.longitude,
                    payload.house_system.encode("ascii"),
                    flags,
                )
            except swe.Error as exc:
                raise RectificationCalculationError(
                    "Failed to calculate ascendant sign",
                    details={"error": str(exc)},
                ) from exc

        sign_index, _, _ = resolve_sign(normalize_degree(ascmc[0]))
        return sign_index

    def _calculate_object_sign(
        self,
        dt_utc: datetime,
        body: int,
        payload: AscSignIntervalsRequest,
    ) -> str:
        jd_ut = self._to_julian_day_ut(dt_utc)
        with SWE_CALC_LOCK:
            flags = self._prepare_swe(payload)
            try:
                body_data, _ = swe.calc_ut(jd_ut, body, flags)
            except swe.Error as exc:
                raise RectificationCalculationError(
                    "Failed to calculate planet sign for summary",
                    details={"body": int(body), "error": str(exc)},
                ) from exc
        _, sign_name, _ = resolve_sign(normalize_degree(body_data[0]))
        return sign_name

    def _refine_sign_boundary(
        self,
        *,
        left: datetime,
        right: datetime,
        from_sign: int,
        payload: AscSignIntervalsRequest,
    ) -> datetime:
        left_sign = from_sign
        right_sign = self._calculate_asc_sign_index(right, payload)
        if right_sign == left_sign:
            return right

        while (right - left) > timedelta(minutes=1):
            midpoint = left + (right - left) / 2
            midpoint_sign = self._calculate_asc_sign_index(midpoint, payload)
            if midpoint_sign == left_sign:
                left = midpoint
            else:
                right = midpoint

        return right.replace(microsecond=0)

    @staticmethod
    def _interpolate_time(start_utc: datetime, end_utc: datetime, *, ratio: float) -> datetime:
        total_seconds = (end_utc - start_utc).total_seconds()
        return start_utc + timedelta(seconds=total_seconds * ratio)

    def _prepare_swe(self, payload: AscSignIntervalsRequest) -> int:
        swe.set_ephe_path(self.ephe_path)
        flags = swe.FLG_SWIEPH | swe.FLG_SPEED
        if payload.zodiac_mode == ZodiacMode.sidereal:
            if payload.sidereal_mode is None:
                raise RectificationCalculationError(
                    "sidereal_mode is required for sidereal zodiac",
                    details={"zodiac_mode": payload.zodiac_mode.value},
                )
            flags |= swe.FLG_SIDEREAL
            swe.set_sid_mode(SIDEREAL_MODE_MAP[payload.sidereal_mode])
        return flags

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

    @staticmethod
    def _to_local_iso(dt_local: datetime) -> str:
        return dt_local.replace(tzinfo=None).isoformat(timespec="seconds")

    @staticmethod
    def _to_utc_z(dt_utc: datetime) -> str:
        return dt_utc.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
