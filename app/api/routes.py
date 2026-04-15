from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.models.request_models import ChartRequest
from app.models.response_models import ChartResponse
from app.services.ephemeris_service import EphemerisService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chart"])


@router.post("/chart", response_model=ChartResponse)
def build_chart(payload: ChartRequest, request: Request) -> ChartResponse:
    logger.info(
        "Chart request received: datetime_utc=%s latitude=%s longitude=%s house_system=%s zodiac_mode=%s",
        payload.datetime_as_z(),
        payload.latitude,
        payload.longitude,
        payload.house_system,
        payload.zodiac_mode.value,
    )
    service: EphemerisService = request.app.state.ephemeris_service
    return service.calculate_chart(payload)

