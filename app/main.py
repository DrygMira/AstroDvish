from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router as chart_router
from app.api.rectification_routes import router as rectification_router
from app.bootstrap_ephe import bootstrap_ephemeris
from app.config import Settings, get_settings
from app.core.errors import AppError
from app.services.asc_sign_intervals_service import AscSignIntervalsService
from app.core.logging import configure_logging
from app.services.ephemeris_service import EphemerisService

logger = logging.getLogger(__name__)


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
        logger.info("Application startup completed")
        yield
        logger.info("Application shutdown completed")

    return lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=_build_lifespan(settings),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.include_router(chart_router)
    app.include_router(rectification_router)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.error("Validation error: %s", exc.errors())
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.error("Application error: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error",
                    "details": str(exc),
                }
            },
        )

    return app


app = create_app()
