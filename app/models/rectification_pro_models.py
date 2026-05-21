from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.event_models import EventCard
from app.models.formula_card_models import FormulaTestModeResult
from app.models.request_models import SiderealMode, ZodiacMode


class ProAscWindow(BaseModel):
    start_local: str
    end_local: str
    sign_name_en: str
    sign_name_ru: str | None = None


class RectificationProSettings(BaseModel):
    candidate_step_minutes: int = 5
    include_directions: bool = True
    include_solars: bool = True
    include_lunars: bool = False
    include_transits: bool = True
    include_totems: bool = False
    max_candidates: int = 720
    directions_orbs: dict[str, float] = Field(
        default_factory=lambda: {"default": 1.0, "luminaries": 1.5, "cusps": 1.0}
    )
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "directions": 0.45,
            "solar": 0.2,
            "transits": 0.2,
            "lunar": 0.1,
            "totem": 0.05,
        }
    )

    @field_validator("candidate_step_minutes")
    @classmethod
    def _validate_step(cls, value: int) -> int:
        if value not in {1, 2, 5, 10, 15}:
            raise ValueError("candidate_step_minutes must be one of 1, 2, 5, 10, 15")
        return value


class RectificationProRunRequest(BaseModel):
    birth_date_local: date
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone_name: str
    house_system: str = Field(default="P", min_length=1, max_length=1)
    zodiac_mode: ZodiacMode = ZodiacMode.tropical
    sidereal_mode: SiderealMode | None = None
    asc_windows: list[ProAscWindow] = Field(default_factory=list)
    events: list[EventCard] = Field(default_factory=list)
    settings: RectificationProSettings = Field(default_factory=RectificationProSettings)


class CandidateTime(BaseModel):
    candidate_id: str
    datetime_local: str
    datetime_utc: str
    asc_sign: str
    asc_degree: float
    source_asc_interval: dict[str, str] | None = None
    clipped_by_birth_date: bool = False


class CandidateGenerationResult(BaseModel):
    candidate_times: list[CandidateTime]
    warnings: list[str] = Field(default_factory=list)


class MethodMatch(BaseModel):
    event_id: str
    method: str
    matches: list[dict[str, Any]] = Field(default_factory=list)
    event_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class CandidateScore(BaseModel):
    candidate_id: str
    candidate_time_local: str
    candidate_window: dict[str, str]
    scores: dict[str, float | None]
    matched_events_count: int
    strong_events_matched_count: int
    confidence_level: Literal["low", "medium", "high", "expert_high"]
    warnings: list[str] = Field(default_factory=list)
    source_asc_interval: dict[str, str] | None = None
    clipped_by_birth_date: bool = False


class ConfidenceSummary(BaseModel):
    level: Literal["low", "medium", "high", "expert_high"]
    time_window_minutes: int
    explanation: str


class RectificationProRunResponse(BaseModel):
    mode: Literal["rectification_pro"] = "rectification_pro"
    version: str = "0.1"
    status: Literal["completed"] = "completed"
    candidate_windows: list[CandidateScore]
    best_candidates: list[CandidateScore]
    method_results: dict[str, list[MethodMatch]]
    formula_test_mode_results: list[FormulaTestModeResult] = Field(default_factory=list)
    confidence: ConfidenceSummary
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
