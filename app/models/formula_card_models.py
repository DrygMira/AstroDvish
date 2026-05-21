from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class FormulaSubformula(BaseModel):
    id: str
    title: str
    indicators: list[str] = Field(default_factory=list)


class FormulaDirectionRule(BaseModel):
    id: str
    title: str
    source_kind: Literal["directed"] = "directed"
    target_kind: Literal["natal"] = "natal"
    source_selectors: list[str] = Field(default_factory=list)
    target_selectors: list[str] = Field(default_factory=list)
    display_source: str | None = None
    display_target: str | None = None
    aspect_types: list[str] = Field(default_factory=list)
    orb_limit: float = 1.0
    required: bool = True
    weight: float = 1.0


class FormulaCard(BaseModel):
    card_id: str
    event_type: str
    status: str
    school: str | None = None
    title: str | None = None
    core_logic: list[str]
    houses: list[str] = Field(default_factory=list)
    planets: list[str] = Field(default_factory=list)
    significators: list[str] = Field(default_factory=list)
    aspects: list[str]
    method_priority: list[str]
    strong_confirmation: list[str] = Field(default_factory=list)
    weak_confirmation: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    subformulas: list[FormulaSubformula] = Field(default_factory=list)
    direction_rules: list[FormulaDirectionRule] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("core_logic", "aspects", "method_priority")
    @classmethod
    def _validate_non_empty_lists(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must not be empty")
        return value


class FormulaAspectMatch(BaseModel):
    method: str
    event_type: str
    card_id: str
    directed_point: str
    natal_target: str
    aspect_type: str
    actual_angle: float
    exact_angle: float
    orb: float
    orb_limit: float
    strength: str
    formula_rule_matched: str
    explanation_for_expert: str
    rejection_reason: str | None = None


class FormulaTestModeResult(BaseModel):
    card_id: str
    event_type: str
    status: str
    source_event_id: str | None = None
    source_event_type: str | None = None
    source_event_title: str | None = None
    source_event_date: str | None = None
    matched_indicators: list[str]
    missing_indicators: list[str]
    weak_indicators: list[str]
    exclusion_risks: list[str]
    methods_used: list[str]
    score: float
    confidence: str
    explanation_for_expert: str
    matched_formula_aspects: list[FormulaAspectMatch] = Field(default_factory=list)
    missing_formula_links: list[dict[str, Any]] = Field(default_factory=list)
    rejected_aspects: list[FormulaAspectMatch] = Field(default_factory=list)
    validation_report: dict[str, Any] = Field(default_factory=dict)
    validation_report_table: str | None = None
    debug: dict[str, Any] = Field(default_factory=dict)
