from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import httpx
from pydantic import BaseModel

from app.models.event_models import (
    EventsDialogContinueRequest,
    EventsDialogFinalResponse,
    EventsDialogFinalizeRequest,
    EventsDialogQuestionResponse,
    EventsDialogStartRequest,
)
from app.models.rectification_models import AscSignIntervalsRequest, AscSignIntervalsResponse
from app.models.request_models import ChartRequest
from app.models.response_models import ChartResponse

T = TypeVar("T")


class AstroDvishClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.details = details


class AstroDvishTimeoutError(AstroDvishClientError):
    pass


class AstroDvishNetworkError(AstroDvishClientError):
    pass


class AstroDvishValidationError(AstroDvishClientError):
    pass


class AstroDvishServerError(AstroDvishClientError):
    pass


class AstroDvishUnexpectedResponseError(AstroDvishClientError):
    pass


@dataclass
class ClientResponse(Generic[T]):
    data: T
    request_id: str | None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    request_id: str | None = None


class AstroDvishClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_safe_retries: int = 1,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_safe_retries = max_safe_retries
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AstroDvishClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_health(self, *, request_id: str | None = None) -> ClientResponse[HealthResponse]:
        payload, response_request_id = self._request(
            method="GET",
            path="/api/v1/health",
            json_payload=None,
            request_id=request_id,
        )
        return ClientResponse(
            data=HealthResponse.model_validate(payload),
            request_id=response_request_id,
        )

    def get_chart(self, payload: ChartRequest, *, request_id: str | None = None) -> ClientResponse[ChartResponse]:
        response_payload, response_request_id = self._request(
            method="POST",
            path="/api/v1/chart",
            json_payload=payload.model_dump(mode="json"),
            request_id=request_id,
        )
        return ClientResponse(
            data=ChartResponse.model_validate(response_payload),
            request_id=response_request_id,
        )

    def get_asc_sign_intervals(
        self,
        payload: AscSignIntervalsRequest,
        *,
        request_id: str | None = None,
    ) -> ClientResponse[AscSignIntervalsResponse]:
        response_payload, response_request_id = self._request(
            method="POST",
            path="/api/v1/rectification/asc-sign-intervals",
            json_payload=payload.model_dump(mode="json"),
            request_id=request_id,
        )
        return ClientResponse(
            data=AscSignIntervalsResponse.model_validate(response_payload),
            request_id=response_request_id,
        )

    def start_events_collection(
        self,
        payload: EventsDialogStartRequest,
        *,
        request_id: str | None = None,
    ) -> ClientResponse[EventsDialogQuestionResponse | EventsDialogFinalResponse]:
        response_payload, response_request_id = self._request(
            method="POST",
            path="/api/v1/rectification/events/start",
            json_payload=payload.model_dump(mode="json"),
            request_id=request_id,
        )
        return ClientResponse(
            data=self._parse_events_response(response_payload),
            request_id=response_request_id,
        )

    def continue_events_collection(
        self,
        payload: EventsDialogContinueRequest,
        *,
        request_id: str | None = None,
    ) -> ClientResponse[EventsDialogQuestionResponse | EventsDialogFinalResponse]:
        response_payload, response_request_id = self._request(
            method="POST",
            path="/api/v1/rectification/events/continue",
            json_payload=payload.model_dump(mode="json"),
            request_id=request_id,
        )
        return ClientResponse(
            data=self._parse_events_response(response_payload),
            request_id=response_request_id,
        )

    def finalize_events_collection(
        self,
        payload: EventsDialogFinalizeRequest,
        *,
        request_id: str | None = None,
    ) -> ClientResponse[EventsDialogFinalResponse]:
        response_payload, response_request_id = self._request(
            method="POST",
            path="/api/v1/rectification/events/finalize",
            json_payload=payload.model_dump(mode="json"),
            request_id=request_id,
        )
        return ClientResponse(
            data=EventsDialogFinalResponse.model_validate(response_payload),
            request_id=response_request_id,
        )

    def _request(
        self,
        *,
        method: str,
        path: str,
        json_payload: dict[str, Any] | None,
        request_id: str | None,
    ) -> tuple[dict[str, Any], str | None]:
        headers: dict[str, str] = {}
        if request_id:
            headers["X-Request-ID"] = request_id

        safe_retry_allowed = method.upper() == "GET"
        attempts = self.max_safe_retries + 1 if safe_retry_allowed else 1
        last_timeout_error: httpx.TimeoutException | None = None
        last_network_error: httpx.NetworkError | None = None

        for attempt in range(attempts):
            try:
                response = self._client.request(
                    method=method,
                    url=path,
                    json=json_payload,
                    headers=headers or None,
                )
            except httpx.TimeoutException as exc:
                last_timeout_error = exc
                if attempt < attempts - 1:
                    continue
                raise AstroDvishTimeoutError(
                    "AstroDvish request timed out",
                    request_id=request_id,
                    details={"path": path, "method": method},
                ) from exc
            except httpx.NetworkError as exc:
                last_network_error = exc
                if attempt < attempts - 1:
                    continue
                raise AstroDvishNetworkError(
                    "AstroDvish network error",
                    request_id=request_id,
                    details={"path": path, "method": method},
                ) from exc

            response_request_id = response.headers.get("X-Request-ID")
            parsed_json = self._try_parse_json(response)

            if response.status_code == 422:
                error = self._extract_error(parsed_json, response)
                raise AstroDvishValidationError(
                    "AstroDvish validation error",
                    status_code=response.status_code,
                    request_id=error.get("request_id") or response_request_id,
                    details=error,
                )
            if response.status_code >= 500:
                error = self._extract_error(parsed_json, response)
                raise AstroDvishServerError(
                    "AstroDvish server error",
                    status_code=response.status_code,
                    request_id=error.get("request_id") or response_request_id,
                    details=error,
                )
            if response.status_code >= 400:
                error = self._extract_error(parsed_json, response)
                raise AstroDvishClientError(
                    "AstroDvish request failed",
                    status_code=response.status_code,
                    request_id=error.get("request_id") or response_request_id,
                    details=error,
                )

            if not isinstance(parsed_json, dict):
                raise AstroDvishUnexpectedResponseError(
                    "AstroDvish returned non-JSON or non-object response",
                    status_code=response.status_code,
                    request_id=response_request_id,
                    details=response.text[:1000],
                )
            return parsed_json, response_request_id

        if last_timeout_error is not None:
            raise AstroDvishTimeoutError("AstroDvish request timed out", request_id=request_id) from last_timeout_error
        if last_network_error is not None:
            raise AstroDvishNetworkError("AstroDvish network error", request_id=request_id) from last_network_error
        raise AstroDvishUnexpectedResponseError("AstroDvish request failed unexpectedly", request_id=request_id)

    @staticmethod
    def _try_parse_json(response: httpx.Response) -> dict[str, Any] | Any:
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _extract_error(parsed_json: Any, response: httpx.Response) -> dict[str, Any]:
        if isinstance(parsed_json, dict):
            if isinstance(parsed_json.get("error"), dict):
                return parsed_json["error"]
            if isinstance(parsed_json.get("detail"), dict):
                return parsed_json["detail"]
            if "detail" in parsed_json:
                return {"message": parsed_json["detail"]}
            return parsed_json
        return {"message": response.text[:1000]}

    @staticmethod
    def _parse_events_response(payload: dict[str, Any]) -> EventsDialogQuestionResponse | EventsDialogFinalResponse:
        status = payload.get("status")
        if status == "ask_question":
            return EventsDialogQuestionResponse.model_validate(payload)
        if status == "finalized":
            return EventsDialogFinalResponse.model_validate(payload)
        raise AstroDvishUnexpectedResponseError(
            "Unexpected events response status",
            details={"status": status, "payload": payload},
        )


def get_chart_for_bot(
    client: AstroDvishClient,
    payload: ChartRequest,
    *,
    request_id: str | None = None,
) -> ClientResponse[ChartResponse]:
    return client.get_chart(payload, request_id=request_id)


def get_asc_intervals_for_bot(
    client: AstroDvishClient,
    payload: AscSignIntervalsRequest,
    *,
    request_id: str | None = None,
) -> ClientResponse[AscSignIntervalsResponse]:
    return client.get_asc_sign_intervals(payload, request_id=request_id)


def start_events_collection(
    client: AstroDvishClient,
    payload: EventsDialogStartRequest,
    *,
    request_id: str | None = None,
) -> ClientResponse[EventsDialogQuestionResponse | EventsDialogFinalResponse]:
    return client.start_events_collection(payload, request_id=request_id)


def continue_events_collection(
    client: AstroDvishClient,
    payload: EventsDialogContinueRequest,
    *,
    request_id: str | None = None,
) -> ClientResponse[EventsDialogQuestionResponse | EventsDialogFinalResponse]:
    return client.continue_events_collection(payload, request_id=request_id)


def finalize_events_collection(
    client: AstroDvishClient,
    payload: EventsDialogFinalizeRequest,
    *,
    request_id: str | None = None,
) -> ClientResponse[EventsDialogFinalResponse]:
    return client.finalize_events_collection(payload, request_id=request_id)

