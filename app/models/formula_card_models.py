from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PriorityTier = Literal["golden", "supporting", "context", "ambiguity_risk"]


class FormulaSubformula(BaseModel):
    id: str
    title: str
    indicators: list[str] = Field(default_factory=list)


class FormulaDirectionRule(BaseModel):
    id: str
    title: str
    formula: str | None = None
    rule: str | None = None
    source: str | None = None
    target: str | None = None
    source_layer: str | None = None
    target_layer: str | None = None
    aspect: str | None = None
    priority: str | None = None
    role: str | None = None
    meaning: str | None = None
    comment: str | None = None
    source_kind: Literal["directed"] = "directed"
    target_kind: Literal["natal"] = "natal"
    source_selectors: list[str] = Field(default_factory=list)
    target_selectors: list[str] = Field(default_factory=list)
    display_source: str | None = None
    display_target: str | None = None
    allowed_aspects: list[str] = Field(default_factory=list)
    allowed_ruler_types: list[str] = Field(default_factory=list)
    aspect_types: list[str] = Field(default_factory=list)
    orb_limit: float = 1.0
    required: bool = True
    weight: float = 1.0
    priority_tier: PriorityTier = "supporting"

    @field_validator("allowed_aspects", "allowed_ruler_types", "aspect_types", mode="before")
    @classmethod
    def _validate_aspect_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raise ValueError("allowed_aspects must be a list")
        return [str(item) for item in value]

    @field_validator("priority_tier", mode="before")
    @classmethod
    def _normalize_priority_tier(cls, value: Any) -> str:
        if value is None:
            return "supporting"
        normalized = str(value).strip().lower()
        mapping = {
            "primary": "golden",
            "golden": "golden",
            "secondary": "supporting",
            "supporting": "supporting",
            "context": "context",
            "ambiguity_risk": "ambiguity_risk",
        }
        if normalized in mapping:
            return mapping[normalized]
        return normalized

    @model_validator(mode="after")
    def _synchronize_formula_fields(self) -> "FormulaDirectionRule":
        if not self.allowed_aspects and self.aspect_types:
            self.allowed_aspects = list(self.aspect_types)
        if not self.aspect_types and self.allowed_aspects:
            self.aspect_types = list(self.allowed_aspects)
        if self.aspect is None and self.aspect_types:
            self.aspect = self.aspect_types[0]
        if self.priority is None:
            self.priority = self.priority_tier
        return self


class FormulaCard(BaseModel):
    card_id: str
    event_type: str
    status: str
    card_version: str | None = None
    card_hash: str | None = None
    source_file_path: str | None = None
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
    direction_method: str | None = None
    direction_arc: float | None = None
    directed_point: str
    directed_point_role: str | None = None
    directed_point_ruler_type: str | None = None
    directed_source_longitude: float | None = None
    natal_target: str
    natal_target_role: str | None = None
    natal_target_ruler_type: str | None = None
    natal_target_longitude: float | None = None
    aspect_type: str
    actual_angle: float
    exact_angle: float
    orb: float
    orb_limit: float
    strength: str
    match_status: str | None = None
    formula_rule_matched: str
    rule_weight: float | None = None
    priority_tier: PriorityTier | None = None
    explanation_for_expert: str
    rejection_reason: str | None = None


class FormulaTestModeResult(BaseModel):
    card_id: str
    event_type: str
    status: str
    card_version: str | None = None
    card_hash: str | None = None
    source_file_path: str | None = None
    formulas_count: int | None = None
    priority_counts: dict[str, int] = Field(default_factory=dict)
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
