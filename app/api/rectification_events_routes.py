from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.models.event_models import (
    EventsDialogContinueRequest,
    EventsDialogFinalResponse,
    EventsDialogFinalizeRequest,
    EventsDialogQuestionResponse,
    EventsDialogStartRequest,
)
from app.services.rectification_events_service import RectificationEventsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/rectification/events", tags=["rectification-events"])


@router.post("/start", response_model=EventsDialogQuestionResponse | EventsDialogFinalResponse)
def events_start(payload: EventsDialogStartRequest, request: Request) -> EventsDialogQuestionResponse | EventsDialogFinalResponse:
    service: RectificationEventsService = request.app.state.rectification_events_service
    return service.start_flow(payload.dialog_history)


@router.post("/continue", response_model=EventsDialogQuestionResponse | EventsDialogFinalResponse)
def events_continue(payload: EventsDialogContinueRequest, request: Request) -> EventsDialogQuestionResponse | EventsDialogFinalResponse:
    service: RectificationEventsService = request.app.state.rectification_events_service
    return service.continue_flow(payload.dialog_history, payload.last_answer)


@router.post("/finalize", response_model=EventsDialogFinalResponse)
def events_finalize(payload: EventsDialogFinalizeRequest, request: Request) -> EventsDialogFinalResponse:
    service: RectificationEventsService = request.app.state.rectification_events_service
    return service.finalize_flow(payload.dialog_history)
