from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.rectification_pro_models import RectificationProRunRequest, RectificationProRunResponse
from app.services.rectification_pro.rectification_pro_service import RectificationProService

router = APIRouter(prefix="/api/v1/rectification/pro", tags=["rectification-pro"])


@router.post("/run", response_model=RectificationProRunResponse)
def rectification_pro_run(payload: RectificationProRunRequest, request: Request) -> RectificationProRunResponse:
    service: RectificationProService = request.app.state.rectification_pro_service
    return service.run(payload)
