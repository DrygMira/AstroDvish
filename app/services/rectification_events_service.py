from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from uuid import uuid4

from app.models.event_models import (
    DatePrecision,
    EventAnswerInput,
    EventCard,
    EventQuestion,
    EventQuestionOption,
    EventType,
    EventsDialogFinalResponse,
    EventsDialogHistoryItem,
    EventsDialogQuestionResponse,
    LifeArea,
    Reversibility,
)

MIN_EVENTS = 3
GOOD_EVENTS_MIN = 5
GOOD_EVENTS_MAX = 7
MAX_EVENTS = 10
MAX_STEPS = 14

EVENT_QUESTION_BANK: list[EventQuestion] = [
    EventQuestion(
        question_id="ev_children_birth_01",
        event_type=EventType.children_birth,
        question_text="Было ли рождение ребенка (или детей), которое сильно изменило вашу жизнь?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_death_close_02",
        event_type=EventType.death_of_close_person,
        question_text="Была ли смерть близкого человека, после которой жизнь разделилась на до/после?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_surgery_accident_03",
        event_type=EventType.surgery_accident_life_risk,
        question_text="Были ли операции, аварии или ситуации с риском для жизни?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_marriage_relationship_04",
        event_type=EventType.marriage_relationship,
        question_text="Было ли официальное оформление брака/развода или крупный перелом в отношениях?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_relocation_05",
        event_type=EventType.relocation_emigration,
        question_text="Был ли переезд, эмиграция или смена города/страны с сильным влиянием?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_education_work_start_06",
        event_type=EventType.education_work_start,
        question_text="Был ли значимый старт в учебе/работе (поступление, первая работа, резкий профессиональный вход)?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_profession_change_07",
        event_type=EventType.profession_lifestyle_change,
        question_text="Была ли радикальная смена профессии или образа жизни?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_freedom_restriction_08",
        event_type=EventType.freedom_restriction,
        question_text="Были ли периоды ограничения свободы (служба, суд, изоляция, длительный уход)?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_finance_rise_fall_09",
        event_type=EventType.financial_rise_fall,
        question_text="Были ли резкие финансовые взлеты/падения?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_inner_crisis_10",
        event_type=EventType.inner_crisis_turning_point,
        question_text="Был ли внутренний кризис или перелом идентичности, после которого вы стали жить иначе?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
    EventQuestion(
        question_id="ev_custom_major_11",
        event_type=EventType.custom_major_event,
        question_text="Есть ли еще одно крупное событие, которое важно учесть?",
        options=[
            EventQuestionOption(id="yes", text="Да"),
            EventQuestionOption(id="no", text="Нет"),
            EventQuestionOption(id="skip", text="Пропустить"),
        ],
    ),
]

EVENT_TYPE_DEFAULT_LIFE_AREA: dict[EventType, LifeArea] = {
    EventType.children_birth: LifeArea.relationships,
    EventType.death_of_close_person: LifeArea.relationships,
    EventType.surgery_accident_life_risk: LifeArea.health,
    EventType.marriage_relationship: LifeArea.relationships,
    EventType.relocation_emigration: LifeArea.home,
    EventType.education_work_start: LifeArea.career,
    EventType.profession_lifestyle_change: LifeArea.career,
    EventType.freedom_restriction: LifeArea.identity,
    EventType.financial_rise_fall: LifeArea.finance,
    EventType.inner_crisis_turning_point: LifeArea.identity,
    EventType.custom_major_event: LifeArea.other,
}

IRREVERSIBLE_EVENT_TYPES: set[EventType] = {
    EventType.children_birth,
    EventType.death_of_close_person,
    EventType.surgery_accident_life_risk,
    EventType.freedom_restriction,
}


class RectificationEventsService:
    def start_flow(self, dialog_history: list[EventsDialogHistoryItem]) -> EventsDialogQuestionResponse | EventsDialogFinalResponse:
        history = list(dialog_history)
        warnings: list[str] = []
        events = self._extract_events(history)
        asked_ids = self._asked_question_ids(history)

        if len(events) >= MAX_EVENTS:
            warnings.append("max_events_reached_safe_finalize")
            return self._build_final(history, warnings)

        next_question = self._next_question(asked_ids)
        if next_question is None:
            return self._build_final(history, warnings)

        step_index = self._assistant_steps_count(history) + 1
        history.append(
            EventsDialogHistoryItem(
                role="assistant",
                step_index=step_index,
                question_id=next_question.question_id,
                event_type=next_question.event_type,
            )
        )
        return EventsDialogQuestionResponse(
            step_index=step_index,
            events_collected_count=len(events),
            warnings=warnings,
            question=next_question,
            dialog_history=history,
        )

    def continue_flow(
        self,
        dialog_history: list[EventsDialogHistoryItem],
        last_answer: EventAnswerInput | None,
    ) -> EventsDialogQuestionResponse | EventsDialogFinalResponse:
        history = list(dialog_history)
        warnings: list[str] = []

        last_question_item = self._last_assistant_question_item(history)
        if last_question_item is None:
            warnings.append("missing_active_question_fallback")
            return self.start_flow(history)
        if last_question_item.question_id is None:
            warnings.append("missing_active_question_fallback")
            return self.start_flow(history)
        last_question = self._find_question_by_id(last_question_item.question_id)
        if last_question is None:
            warnings.append("missing_active_question_fallback")
            return self.start_flow(history)

        if last_answer is None:
            warnings.append("empty_answer_retry")
            return self._retry_same_question(
                history,
                last_question,
                last_question_item.step_index,
                warnings,
            )

        if last_answer.question_id != last_question.question_id:
            warnings.append("question_mismatch_retry")
            return self._retry_same_question(
                history,
                last_question,
                last_question_item.step_index,
                warnings,
            )

        if not last_answer.user_skipped and self._is_answer_empty(last_answer):
            warnings.append("empty_answer_retry")
            return self._retry_same_question(
                history,
                last_question,
                last_question_item.step_index,
                warnings,
            )

        user_event = self._build_event_card(last_answer)
        history.append(
            EventsDialogHistoryItem(
                role="user",
                step_index=last_question_item.step_index,
                question_id=last_answer.question_id,
                event_type=last_answer.event_type,
                event=user_event,
                user_skipped=last_answer.user_skipped,
                raw_answer=last_answer.model_dump(),
            )
        )

        events = self._extract_events(history)
        asked_ids = self._asked_question_ids(history)
        step_count = self._assistant_steps_count(history)

        if len(events) >= MAX_EVENTS:
            warnings.append("max_events_reached_safe_finalize")
            return self._build_final(history, warnings)

        if step_count >= MAX_STEPS:
            warnings.append("max_steps_reached_safe_finalize")
            return self._build_final(history, warnings)

        next_question = self._next_question(asked_ids)
        if next_question is None:
            return self._build_final(history, warnings)

        next_step_index = step_count + 1
        history.append(
            EventsDialogHistoryItem(
                role="assistant",
                step_index=next_step_index,
                question_id=next_question.question_id,
                event_type=next_question.event_type,
            )
        )
        return EventsDialogQuestionResponse(
            step_index=next_step_index,
            events_collected_count=len(events),
            warnings=warnings,
            question=next_question,
            dialog_history=history,
        )

    def finalize_flow(self, dialog_history: list[EventsDialogHistoryItem]) -> EventsDialogFinalResponse:
        return self._build_final(list(dialog_history), warnings=[])

    def _build_final(self, history: list[EventsDialogHistoryItem], warnings: list[str]) -> EventsDialogFinalResponse:
        events = self._extract_events(history)
        events_count = len(events)
        strong_events_count = sum(1 for event in events if event.impact_level >= 4)

        if events_count < GOOD_EVENTS_MIN:
            confidence = "low"
            if events_count < MIN_EVENTS:
                warnings = [*warnings, "insufficient_events_minimum_not_reached"]
        elif events_count <= GOOD_EVENTS_MAX:
            confidence = "medium"
        else:
            confidence = "high"

        return EventsDialogFinalResponse(
            step_index=self._assistant_steps_count(history),
            events_collected_count=events_count,
            warnings=warnings,
            events=events,
            events_count=events_count,
            strong_events_count=strong_events_count,
            confidence_preliminary=confidence,
            dialog_history=history,
        )

    def _retry_same_question(
        self,
        history: list[EventsDialogHistoryItem],
        question: EventQuestion,
        step_index: int | None,
        warnings: list[str],
    ) -> EventsDialogQuestionResponse:
        effective_step_index = step_index or self._assistant_steps_count(history)
        return EventsDialogQuestionResponse(
            step_index=effective_step_index,
            events_collected_count=len(self._extract_events(history)),
            warnings=warnings,
            question=question,
            dialog_history=history,
        )

    @staticmethod
    def _extract_events(history: list[EventsDialogHistoryItem]) -> list[EventCard]:
        events: list[EventCard] = []
        for item in history:
            if item.role != "user":
                continue
            if item.event is None:
                continue
            if item.event.user_skipped:
                continue
            events.append(item.event)
        return events

    @staticmethod
    def _asked_question_ids(history: list[EventsDialogHistoryItem]) -> set[str]:
        result: set[str] = set()
        for item in history:
            if item.role != "assistant":
                continue
            if item.question_id:
                result.add(item.question_id)
        return result

    @staticmethod
    def _assistant_steps_count(history: list[EventsDialogHistoryItem]) -> int:
        return sum(1 for item in history if item.role == "assistant")

    def _next_question(self, asked_ids: set[str]) -> EventQuestion | None:
        for question in EVENT_QUESTION_BANK:
            if question.question_id not in asked_ids:
                return question
        return None

    @staticmethod
    def _last_assistant_question_item(history: list[EventsDialogHistoryItem]) -> EventsDialogHistoryItem | None:
        for item in reversed(history):
            if item.role != "assistant":
                continue
            if item.question_id is None or item.event_type is None:
                continue
            return item
        return None

    @staticmethod
    def _find_question_by_id(question_id: str) -> EventQuestion | None:
        for question in EVENT_QUESTION_BANK:
            if question.question_id == question_id:
                return question
        return None

    @staticmethod
    def _is_answer_empty(answer: EventAnswerInput) -> bool:
        title = (answer.title or "").strip()
        date_text = (answer.date_text or "").strip()
        notes = (answer.notes or "").strip()
        return not title and not date_text and not notes

    def _build_event_card(self, answer: EventAnswerInput) -> EventCard:
        if answer.user_skipped:
            return EventCard(
                event_id=str(uuid4()),
                event_type=answer.event_type,
                title="",
                date_text=answer.date_text or "",
                date_precision=DatePrecision.unknown,
                start_date=None,
                end_date=None,
                impact_level=1,
                reversibility=Reversibility.unknown,
                life_area=answer.life_area or EVENT_TYPE_DEFAULT_LIFE_AREA[answer.event_type],
                notes=answer.notes or "",
                user_skipped=True,
            )

        date_text = (answer.date_text or "").strip()
        date_precision, start_date, end_date = self._parse_date_text(date_text)
        impact_level = self._resolve_impact(answer)

        title = (answer.title or "").strip()
        if not title:
            title = self._default_title(answer.event_type)

        reversibility = answer.reversibility
        if reversibility is None:
            reversibility = (
                Reversibility.irreversible
                if answer.event_type in IRREVERSIBLE_EVENT_TYPES
                else Reversibility.reversible
            )

        life_area = answer.life_area or EVENT_TYPE_DEFAULT_LIFE_AREA[answer.event_type]

        return EventCard(
            event_id=str(uuid4()),
            event_type=answer.event_type,
            title=title,
            date_text=date_text,
            date_precision=date_precision,
            start_date=start_date,
            end_date=end_date,
            impact_level=impact_level,
            reversibility=reversibility,
            life_area=life_area,
            notes=(answer.notes or "").strip(),
            user_skipped=False,
        )

    @staticmethod
    def _default_title(event_type: EventType) -> str:
        return event_type.value

    @staticmethod
    def _resolve_impact(answer: EventAnswerInput) -> int:
        if answer.impact_level is not None:
            return max(1, min(5, answer.impact_level))

        if answer.event_type in {
            EventType.death_of_close_person,
            EventType.surgery_accident_life_risk,
            EventType.freedom_restriction,
            EventType.inner_crisis_turning_point,
        }:
            return 5
        if answer.event_type in {
            EventType.children_birth,
            EventType.marriage_relationship,
            EventType.relocation_emigration,
            EventType.profession_lifestyle_change,
            EventType.financial_rise_fall,
        }:
            return 4
        return 3

    def _parse_date_text(self, date_text: str) -> tuple[DatePrecision, str | None, str | None]:
        if not date_text:
            return DatePrecision.unknown, None, None

        exact_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_text)
        if exact_match:
            parsed_date = date.fromisoformat(date_text)
            iso_value = parsed_date.isoformat()
            return DatePrecision.exact, iso_value, iso_value

        month_match = re.fullmatch(r"(\d{4})-(\d{2})", date_text)
        if month_match:
            year = int(month_match.group(1))
            month = int(month_match.group(2))
            start = date(year, month, 1)
            last_day = monthrange(year, month)[1]
            end = date(year, month, last_day)
            return DatePrecision.month, start.isoformat(), end.isoformat()

        year_match = re.fullmatch(r"(\d{4})", date_text)
        if year_match:
            year = int(year_match.group(1))
            start = date(year, 1, 1)
            end = date(year, 12, 31)
            return DatePrecision.year, start.isoformat(), end.isoformat()

        range_exact_match = re.fullmatch(
            r"(\d{4}-\d{2}-\d{2})\s*(?:\.\.|-|—|–)\s*(\d{4}-\d{2}-\d{2})",
            date_text,
        )
        if range_exact_match:
            start = date.fromisoformat(range_exact_match.group(1))
            end = date.fromisoformat(range_exact_match.group(2))
            return DatePrecision.range, start.isoformat(), end.isoformat()

        range_year_match = re.fullmatch(r"(\d{4})\s*(?:\.\.|-|—|–)\s*(\d{4})", date_text)
        if range_year_match:
            start = date(int(range_year_match.group(1)), 1, 1)
            end = date(int(range_year_match.group(2)), 12, 31)
            return DatePrecision.range, start.isoformat(), end.isoformat()

        return DatePrecision.unknown, None, None
