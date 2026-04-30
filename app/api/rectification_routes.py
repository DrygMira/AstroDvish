from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.models.rectification_models import AscSignIntervalsRequest, AscSignIntervalsResponse
from app.services.asc_sign_intervals_service import AscSignIntervalsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/rectification", tags=["rectification"])


@router.post("/asc-sign-intervals", response_model=AscSignIntervalsResponse)
def asc_sign_intervals(payload: AscSignIntervalsRequest, request: Request) -> AscSignIntervalsResponse:
    logger.info(
        "Rectification request received: birth_date_local=%s latitude=%s longitude=%s house_system=%s zodiac_mode=%s",
        payload.birth_date_local.isoformat(),
        payload.latitude,
        payload.longitude,
        payload.house_system,
        payload.zodiac_mode.value,
    )
    service: AscSignIntervalsService = request.app.state.asc_sign_intervals_service
    return service.calculate_intervals(payload)
