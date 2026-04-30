from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    children_birth = "children_birth"
    death_of_close_person = "death_of_close_person"
    surgery_accident_life_risk = "surgery_accident_life_risk"
    marriage_relationship = "marriage_relationship"
    relocation_emigration = "relocation_emigration"
    education_work_start = "education_work_start"
    profession_lifestyle_change = "profession_lifestyle_change"
    freedom_restriction = "freedom_restriction"
    financial_rise_fall = "financial_rise_fall"
    inner_crisis_turning_point = "inner_crisis_turning_point"
    custom_major_event = "custom_major_event"


class DatePrecision(str, Enum):
    exact = "exact"
    month = "month"
    year = "year"
    range = "range"
    unknown = "unknown"


class Reversibility(str, Enum):
    reversible = "reversible"
    irreversible = "irreversible"
    unknown = "unknown"


class LifeArea(str, Enum):
    relationships = "relationships"
    career = "career"
    home = "home"
    health = "health"
    finance = "finance"
    identity = "identity"
    other = "other"


class EventCard(BaseModel):
    event_id: str
    event_type: EventType
    title: str
    date_text: str
    date_precision: DatePrecision
    start_date: str | None = None
    end_date: str | None = None
    impact_level: int = Field(ge=1, le=5)
    reversibility: Reversibility
    life_area: LifeArea
    notes: str = ""
    user_skipped: bool = False


class EventQuestionOption(BaseModel):
    id: str
    text: str


class EventQuestion(BaseModel):
    question_id: str
    event_type: EventType
    question_text: str
    options: list[EventQuestionOption]


class EventsDialogHistoryItem(BaseModel):
    role: Literal["assistant", "user"]
    step_index: int | None = None
    question_id: str | None = None
    event_type: EventType | None = None
    event: EventCard | None = None
    user_skipped: bool | None = None
    raw_answer: dict[str, Any] | None = None


class EventsDialogStartRequest(BaseModel):
    dialog_history: list[EventsDialogHistoryItem] = Field(default_factory=list)


class EventAnswerInput(BaseModel):
    question_id: str
    event_type: EventType
    title: str | None = None
    date_text: str | None = None
    impact_level: int | None = None
    reversibility: Reversibility | None = None
    life_area: LifeArea | None = None
    notes: str | None = None
    user_skipped: bool = False

    @field_validator("impact_level")
    @classmethod
    def _validate_impact_level(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 1 or value > 5:
            raise ValueError("impact_level must be in range 1..5")
        return value


class EventsDialogContinueRequest(BaseModel):
    dialog_history: list[EventsDialogHistoryItem] = Field(default_factory=list)
    last_answer: EventAnswerInput | None = None


class EventsDialogFinalizeRequest(BaseModel):
    dialog_history: list[EventsDialogHistoryItem] = Field(default_factory=list)


class EventsFlowResponseBase(BaseModel):
    step_index: int
    events_collected_count: int
    warnings: list[str] = Field(default_factory=list)


class EventsDialogQuestionResponse(EventsFlowResponseBase):
    status: Literal["ask_question"] = "ask_question"
    question: EventQuestion
    dialog_history: list[EventsDialogHistoryItem]


class EventsDialogFinalResponse(EventsFlowResponseBase):
    status: Literal["finalized"] = "finalized"
    events: list[EventCard]
    events_count: int
    strong_events_count: int
    confidence_preliminary: Literal["low", "medium", "high"]
    dialog_history: list[EventsDialogHistoryItem]
