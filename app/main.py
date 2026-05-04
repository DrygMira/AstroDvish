from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router as chart_router
from app.api.rectification_routes import router as rectification_router
from app.api.rectification_events_routes import router as rectification_events_router
from app.api.rectification_pro_routes import router as rectification_pro_router
from app.bootstrap_ephe import bootstrap_ephemeris
from app.config import Settings, get_settings
from app.core.errors import AppError
from app.services.asc_sign_intervals_service import AscSignIntervalsService
from app.core.logging import configure_logging
from app.services.ephemeris_service import EphemerisService
from app.services.rectification_events_service import RectificationEventsService
from app.services.rectification_pro.rectification_pro_service import RectificationProService

logger = logging.getLogger(__name__)
APP_VERSION_PATH = Path(__file__).resolve().parent.parent / "VERSION"
APP_VERSION = APP_VERSION_PATH.read_text(encoding="utf-8").strip() if APP_VERSION_PATH.exists() else "0.5.0"


def _request_id_from_request(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) and request_id else None


def _log_event(event: str, **fields: object) -> None:
    logger.info(
        json.dumps(
            {
                "event": event,
                **fields,
            },
            ensure_ascii=False,
            default=str,
        )
    )


def _build_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting %s", settings.app_name)
        report = bootstrap_ephemeris(settings)
        if report.missing_files and settings.sweph_auto_download is False:
            logger.warning(
                "Service started with missing ephemeris files and auto-download disabled: %s",
                report.missing_files,
            )
        app.state.ephemeris_service = EphemerisService(str(settings.sweph_ephe_path))
        app.state.asc_sign_intervals_service = AscSignIntervalsService(str(settings.sweph_ephe_path))
        app.state.rectification_events_service = RectificationEventsService()
        app.state.rectification_pro_service = RectificationProService(app.state.ephemeris_service)
        logger.info("Application startup completed")
        yield
        logger.info("Application shutdown completed")

    return lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)

    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        lifespan=_build_lifespan(settings),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.include_router(chart_router)
    app.include_router(rectification_router)
    app.include_router(rectification_events_router)
    app.include_router(rectification_pro_router)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "").strip() or str(uuid.uuid4())
        request.state.request_id = request_id

        started = time.perf_counter()
        _log_event(
            "request_start",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            _log_event(
                "request_exception",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=elapsed_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        response.headers["X-Request-ID"] = request_id
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        _log_event(
            "request_end",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=elapsed_ms,
        )
        return response

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        payload = {
            "status": "ok",
            "service": "astrodvish-api",
            "version": app.version,
        }
        request_id = _request_id_from_request(request)
        if request_id:
            payload["request_id"] = request_id
        return JSONResponse(content=payload)

    @app.get("/api/v1/health")
    async def api_v1_health(request: Request) -> JSONResponse:
        payload = {
            "status": "ok",
            "service": "astrodvish-api",
            "version": app.version,
        }
        request_id = _request_id_from_request(request)
        if request_id:
            payload["request_id"] = request_id
        return JSONResponse(content=payload)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _request_id_from_request(request)
        logger.error("Validation error: %s", exc.errors())
        return JSONResponse(
            status_code=422,
            headers={"X-Request-ID": request_id} if request_id else None,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": jsonable_encoder(exc.errors()),
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = _request_id_from_request(request)
        logger.error("Application error: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            headers={"X-Request-ID": request_id} if request_id else None,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id_from_request(request)
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": request_id} if request_id else None,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error",
                    "details": str(exc),
                    "request_id": request_id,
                }
            },
        )

    return app


app = create_app()
