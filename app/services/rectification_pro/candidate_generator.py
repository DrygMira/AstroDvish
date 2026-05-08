from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.rectification_pro_models import CandidateGenerationResult, CandidateTime, ProAscWindow


class CandidateGenerator:
    def generate(
        self,
        *,
        birth_date_local: date,
        timezone_name: str,
        asc_windows: list[ProAscWindow],
        step_minutes: int,
        max_candidates: int,
    ) -> CandidateGenerationResult:
        warnings: list[str] = []
        tz = ZoneInfo(timezone_name)
        candidate_times: list[CandidateTime] = []
        day_start = datetime.combine(birth_date_local, time(0, 0, 0))
        day_end = day_start + timedelta(days=1)
        had_clipped_windows = False

        step = timedelta(minutes=step_minutes)
        next_id = 1
        for window in asc_windows:
            start_local = datetime.fromisoformat(window.start_local)
            end_local = datetime.fromisoformat(window.end_local)
            if end_local <= start_local:
                warnings.append(f"invalid_window_skipped:{window.start_local}..{window.end_local}")
                continue

            clipped_start = max(start_local, day_start)
            clipped_end = min(end_local, day_end)
            was_clipped = clipped_start != start_local or clipped_end != end_local
            if was_clipped:
                had_clipped_windows = True

            if clipped_end <= clipped_start:
                warnings.append(f"window_outside_birth_date_skipped:{window.start_local}..{window.end_local}")
                continue

            duration_minutes = int((clipped_end - clipped_start).total_seconds() // 60)
            if duration_minutes > 180:
                warnings.append("candidate_window_is_large")

            probe = clipped_start
            while probe <= clipped_end:
                if probe < day_start:
                    probe += step
                    continue
                if probe >= day_end:
                    break
                if len(candidate_times) >= max_candidates:
                    warnings.append("max_candidates_limit_reached")
                    if had_clipped_windows:
                        warnings.append("candidate_windows_clipped_to_birth_date")
                    return CandidateGenerationResult(candidate_times=candidate_times, warnings=warnings)
                local_aware = probe.replace(tzinfo=tz)
                utc_dt = local_aware.astimezone(timezone.utc)
                asc_degree = self._estimate_asc_degree(clipped_start, clipped_end, probe)
                candidate_times.append(
                    CandidateTime(
                        candidate_id=f"cand_{next_id:03d}",
                        datetime_local=probe.isoformat(timespec="seconds"),
                        datetime_utc=utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
                        asc_sign=window.sign_name_en,
                        asc_degree=asc_degree,
                        source_asc_interval={
                            "start_local": window.start_local,
                            "end_local": window.end_local,
                            "sign_name_en": window.sign_name_en,
                            "sign_name_ru": window.sign_name_ru or "",
                            "start_local_clipped": clipped_start.isoformat(timespec="seconds"),
                            "end_local_clipped": clipped_end.isoformat(timespec="seconds"),
                        },
                        clipped_by_birth_date=was_clipped,
                    )
                )
                next_id += 1
                probe += step

        if had_clipped_windows:
            warnings.append("candidate_windows_clipped_to_birth_date")
        return CandidateGenerationResult(candidate_times=candidate_times, warnings=warnings)

    @staticmethod
    def _estimate_asc_degree(start_local: datetime, end_local: datetime, probe_local: datetime) -> float:
        total = max((end_local - start_local).total_seconds(), 1.0)
        elapsed = max((probe_local - start_local).total_seconds(), 0.0)
        ratio = min(max(elapsed / total, 0.0), 1.0)
        return round(ratio * 30.0, 4)
