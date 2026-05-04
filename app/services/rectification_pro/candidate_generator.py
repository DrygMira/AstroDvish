from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.rectification_pro_models import CandidateGenerationResult, CandidateTime, ProAscWindow


class CandidateGenerator:
    def generate(
        self,
        *,
        timezone_name: str,
        asc_windows: list[ProAscWindow],
        step_minutes: int,
        max_candidates: int,
    ) -> CandidateGenerationResult:
        warnings: list[str] = []
        tz = ZoneInfo(timezone_name)
        candidate_times: list[CandidateTime] = []

        step = timedelta(minutes=step_minutes)
        next_id = 1
        for window in asc_windows:
            start_local = datetime.fromisoformat(window.start_local)
            end_local = datetime.fromisoformat(window.end_local)
            if end_local <= start_local:
                warnings.append(f"invalid_window_skipped:{window.start_local}..{window.end_local}")
                continue

            duration_minutes = int((end_local - start_local).total_seconds() // 60)
            if duration_minutes > 180:
                warnings.append("candidate_window_is_large")

            probe = start_local
            while probe <= end_local:
                if len(candidate_times) >= max_candidates:
                    warnings.append("max_candidates_limit_reached")
                    return CandidateGenerationResult(candidate_times=candidate_times, warnings=warnings)
                local_aware = probe.replace(tzinfo=tz)
                utc_dt = local_aware.astimezone(timezone.utc)
                asc_degree = self._estimate_asc_degree(start_local, end_local, probe)
                candidate_times.append(
                    CandidateTime(
                        candidate_id=f"cand_{next_id:03d}",
                        datetime_local=probe.isoformat(timespec="seconds"),
                        datetime_utc=utc_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
                        asc_sign=window.sign_name_en,
                        asc_degree=asc_degree,
                    )
                )
                next_id += 1
                probe += step

        return CandidateGenerationResult(candidate_times=candidate_times, warnings=warnings)

    @staticmethod
    def _estimate_asc_degree(start_local: datetime, end_local: datetime, probe_local: datetime) -> float:
        total = max((end_local - start_local).total_seconds(), 1.0)
        elapsed = max((probe_local - start_local).total_seconds(), 0.0)
        ratio = min(max(elapsed / total, 0.0), 1.0)
        return round(ratio * 30.0, 4)
