from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        code: str = "internal_error",
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


class EphemerisBootstrapError(AppError):
    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(
            message,
            status_code=500,
            code="ephemeris_bootstrap_error",
            details=details,
        )


class EphemerisCalculationError(AppError):
    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(
            message,
            status_code=500,
            code="ephemeris_calculation_error",
            details=details,
        )


class TimezoneLookupError(AppError):
    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(
            message,
            status_code=422,
            code="timezone_lookup_error",
            details=details,
        )


class RectificationCalculationError(AppError):
    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(
            message,
            status_code=500,
            code="rectification_calculation_error",
            details=details,
        )
