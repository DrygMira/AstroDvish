from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class FormulaSubformula(BaseModel):
    id: str
    title: str
    indicators: list[str] = Field(default_factory=list)


class FormulaCard(BaseModel):
    card_id: str
    event_type: str
    status: str
    school: str | None = None
    title: str | None = None
    core_logic: list[str]
    houses: list[str] = Field(default_factory=list)
    planets: list[str] = Field(default_factory=list)
    aspects: list[str]
    method_priority: list[str]
    strong_confirmation: list[str] = Field(default_factory=list)
    weak_confirmation: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    subformulas: list[FormulaSubformula] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("core_logic", "aspects", "method_priority")
    @classmethod
    def _validate_non_empty_lists(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must not be empty")
        return value


class FormulaTestModeResult(BaseModel):
    card_id: str
    event_type: str
    status: str
    matched_indicators: list[str]
    missing_indicators: list[str]
    weak_indicators: list[str]
    exclusion_risks: list[str]
    methods_used: list[str]
    score: float
    confidence: str
    explanation_for_expert: str
    debug: dict[str, Any] = Field(default_factory=dict)
