from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.clients.astrobot_client import (
    AstroDvishClient,
    AstroDvishServerError,
    AstroDvishTimeoutError,
    AstroDvishValidationError,
    continue_events_collection,
    finalize_events_collection,
    get_asc_intervals_for_bot,
    get_chart_for_bot,
    start_events_collection,
)
from app.models.event_models import (
    EventAnswerInput,
    EventsDialogContinueRequest,
    EventsDialogFinalizeRequest,
    EventsDialogStartRequest,
)
from app.models.rectification_models import AscSignIntervalsRequest
from app.models.request_models import ChartRequest


def _chart_response_payload() -> dict:
    return {
        "input": {
            "datetime_utc": "1984-11-13T11:35:00Z",
            "latitude": 53.9006,
            "longitude": 27.559,
            "house_system": "P",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
        },
        "normalized": {"julian_day_ut": 2446017.98},
        "objects": {
            "sun": {
                "name": "sun",
                "longitude_deg": 120.0,
                "latitude_deg": 0.0,
                "distance_au": 1.0,
                "speed_longitude_deg_per_day": 1.0,
                "retrograde": False,
                "sign_index": 4,
                "sign_name_en": "Leo",
                "sign_degree": 0.0,
                "sign_degree_dms": "0°00'00\"",
                "absolute_degree_0_360": 120.0,
            },
            "moon": {
                "name": "moon",
                "longitude_deg": 180.0,
                "latitude_deg": 0.0,
                "distance_au": 0.0025,
                "speed_longitude_deg_per_day": 12.0,
                "retrograde": False,
                "sign_index": 6,
                "sign_name_en": "Libra",
                "sign_degree": 0.0,
                "sign_degree_dms": "0°00'00\"",
                "absolute_degree_0_360": 180.0,
            },
        },
        "aspects": [
            {
                "object_a": "Sun",
                "object_b": "Moon",
                "aspect_type": "sextile",
                "exact_angle": 60.0,
                "actual_angle": 60.0,
                "orb": 0.0,
                "applying": None,
            }
        ],
        "houses": {
            "system": "P",
            "cusps": {str(i): float(i * 30 % 360) for i in range(1, 13)},
        },
        "angles": {"asc": 100.0, "mc": 200.0},
        "meta": {
            "ephemeris_source": "swisseph",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
            "object_constants": {"sun": 0, "moon": 1},
        },
    }


def _asc_intervals_response_payload() -> dict:
    return {
        "mode": "asc_sign_intervals",
        "version": "1.0",
        "generated_at_utc": "2026-04-29T10:00:00Z",
        "birth_context": {
            "birth_date_local": "2000-04-16",
            "latitude": 53.9,
            "longitude": 27.56667,
            "timezone": "Europe/Minsk",
            "timezone_source": "coordinates",
            "house_system": "P",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
        },
        "day_window": {"start_local": "2000-04-16T00:00:00", "end_local": "2000-04-16T23:59:59"},
        "day_window_utc": {"start_utc": "2000-04-15T21:00:00Z", "end_utc": "2000-04-16T20:59:59Z"},
        "shared_day_summary": {
            "sun_sign": "Aries",
            "moon_sign_start": "Cancer",
            "moon_sign_end": "Leo",
            "moon_changes_sign_today": True,
            "mercury_sign": "Aries",
            "venus_sign": "Taurus",
            "mars_sign": "Gemini",
            "jupiter_sign": "Taurus",
            "saturn_sign": "Taurus",
        },
        "asc_sign_intervals": [
            {
                "interval_index": 1,
                "sign_index": 0,
                "sign_name_en": "Aries",
                "sign_name_ru": "Овен",
                "start_local": "2000-04-15T23:44:00",
                "end_local": "2000-04-16T01:39:00",
                "duration_minutes": 115,
                "sample_points": {
                    "p15": {
                        "local_time": "2000-04-16T00:01:00",
                        "asc_degree_in_sign": 4.2,
                        "moon_sign": "Cancer",
                        "mc_sign": "Capricorn",
                    },
                    "p50": {
                        "local_time": "2000-04-16T00:41:00",
                        "asc_degree_in_sign": 14.9,
                        "moon_sign": "Cancer",
                        "mc_sign": "Aquarius",
                    },
                    "p85": {
                        "local_time": "2000-04-16T01:21:00",
                        "asc_degree_in_sign": 26.1,
                        "moon_sign": "Cancer",
                        "mc_sign": "Aquarius",
                    },
                },
                "changing_features_within_interval": ["asc_degree_change"],
            }
        ],
    }


def test_successful_chart_call_and_request_id_propagation() -> None:
    seen_request_ids: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_request_ids.append(request.headers.get("X-Request-ID"))
        assert request.url.path == "/api/v1/chart"
        return httpx.Response(
            status_code=200,
            json=_chart_response_payload(),
            headers={"X-Request-ID": "rid-chart-response"},
        )

    transport = httpx.MockTransport(handler)
    with AstroDvishClient(base_url="http://test", transport=transport) as client:
        result = get_chart_for_bot(
            client,
            ChartRequest(
                datetime_utc="1984-11-13T11:35:00Z",
                latitude=53.9006,
                longitude=27.5590,
                house_system="P",
                zodiac_mode="tropical",
                sidereal_mode=None,
            ),
            request_id="rid-chart-request",
        )

    assert seen_request_ids == ["rid-chart-request"]
    assert result.request_id == "rid-chart-response"
    assert result.data.meta.ephemeris_source == "swisseph"
    assert result.data.aspects


def test_asc_intervals_call_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/rectification/asc-sign-intervals"
        return httpx.Response(
            status_code=200,
            json=_asc_intervals_response_payload(),
            headers={"X-Request-ID": "rid-asc-response"},
        )

    transport = httpx.MockTransport(handler)
    with AstroDvishClient(base_url="http://test", transport=transport) as client:
        result = get_asc_intervals_for_bot(
            client,
            AscSignIntervalsRequest(
                birth_date_local=date(2000, 4, 16),
                latitude=53.9,
                longitude=27.56667,
                house_system="P",
                zodiac_mode="tropical",
                sidereal_mode=None,
            ),
            request_id="rid-asc-request",
        )

    assert result.request_id == "rid-asc-response"
    assert result.data.birth_context.timezone_source == "coordinates"


def test_events_flow_start_continue_finalize() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/rectification/events/start":
            return httpx.Response(
                status_code=200,
                json={
                    "status": "ask_question",
                    "step_index": 1,
                    "events_collected_count": 0,
                    "warnings": [],
                    "question": {
                        "question_id": "ev_children_birth_01",
                        "event_type": "children_birth",
                        "question_text": "question text",
                        "options": [{"id": "yes", "text": "Да"}],
                    },
                    "dialog_history": [
                        {
                            "role": "assistant",
                            "step_index": 1,
                            "question_id": "ev_children_birth_01",
                            "event_type": "children_birth",
                            "event": None,
                            "user_skipped": None,
                            "raw_answer": None,
                        }
                    ],
                },
                headers={"X-Request-ID": "rid-start"},
            )
        if request.url.path == "/api/v1/rectification/events/continue":
            return httpx.Response(
                status_code=200,
                json={
                    "status": "ask_question",
                    "step_index": 2,
                    "events_collected_count": 1,
                    "warnings": [],
                    "question": {
                        "question_id": "ev_death_close_02",
                        "event_type": "death_of_close_person",
                        "question_text": "next question",
                        "options": [{"id": "yes", "text": "Да"}],
                    },
                    "dialog_history": [],
                },
                headers={"X-Request-ID": "rid-continue"},
            )
        if request.url.path == "/api/v1/rectification/events/finalize":
            return httpx.Response(
                status_code=200,
                json={
                    "status": "finalized",
                    "step_index": 2,
                    "events_collected_count": 1,
                    "warnings": [],
                    "events": [
                        {
                            "event_id": "uuid-1",
                            "event_type": "children_birth",
                            "title": "event title",
                            "date_text": "2018",
                            "date_precision": "year",
                            "start_date": "2018-01-01",
                            "end_date": "2018-12-31",
                            "impact_level": 5,
                            "reversibility": "irreversible",
                            "life_area": "relationships",
                            "notes": "note",
                            "user_skipped": False,
                        }
                    ],
                    "events_count": 1,
                    "strong_events_count": 1,
                    "confidence_preliminary": "low",
                    "dialog_history": [],
                },
                headers={"X-Request-ID": "rid-finalize"},
            )
        return httpx.Response(status_code=404, json={"error": {"message": "not found"}})

    transport = httpx.MockTransport(handler)
    with AstroDvishClient(base_url="http://test", transport=transport) as client:
        start_result = start_events_collection(client, EventsDialogStartRequest(dialog_history=[]))
        assert start_result.data.status == "ask_question"

        continue_result = continue_events_collection(
            client,
            EventsDialogContinueRequest(
                dialog_history=[],
                last_answer=EventAnswerInput(
                    question_id="ev_children_birth_01",
                    event_type="children_birth",
                    title="event title",
                    date_text="2018",
                    impact_level=5,
                    notes="note",
                    user_skipped=False,
                ),
            ),
        )
        assert continue_result.data.status == "ask_question"

        finalize_result = finalize_events_collection(client, EventsDialogFinalizeRequest(dialog_history=[]))
        assert finalize_result.data.status == "finalized"
        assert finalize_result.data.events_count == 1


def test_timeout_handling_raises_timeout_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    transport = httpx.MockTransport(handler)
    with AstroDvishClient(base_url="http://test", transport=transport) as client:
        with pytest.raises(AstroDvishTimeoutError):
            get_chart_for_bot(
                client,
                ChartRequest(
                    datetime_utc="1984-11-13T11:35:00Z",
                    latitude=53.9006,
                    longitude=27.5590,
                    house_system="P",
                    zodiac_mode="tropical",
                    sidereal_mode=None,
                ),
            )


def test_422_handling_raises_validation_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=422,
            json={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "request_id": "rid-422",
                }
            },
            headers={"X-Request-ID": "rid-422-header"},
        )

    transport = httpx.MockTransport(handler)
    with AstroDvishClient(base_url="http://test", transport=transport) as client:
        with pytest.raises(AstroDvishValidationError) as exc:
            client.get_health()

    assert exc.value.request_id == "rid-422"
    assert exc.value.status_code == 422


def test_500_handling_raises_server_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=500,
            json={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error",
                    "request_id": "rid-500",
                }
            },
            headers={"X-Request-ID": "rid-500-header"},
        )

    transport = httpx.MockTransport(handler)
    with AstroDvishClient(base_url="http://test", transport=transport) as client:
        with pytest.raises(AstroDvishServerError) as exc:
            client.get_health()

    assert exc.value.request_id == "rid-500"
    assert exc.value.status_code == 500


def test_retry_only_for_safe_get_requests() -> None:
    attempts = {"health": 0, "chart": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/health":
            attempts["health"] += 1
            if attempts["health"] == 1:
                raise httpx.ReadTimeout("timeout")
            return httpx.Response(status_code=200, json={"status": "ok", "service": "astrodvish-api", "version": "1.0.0"})
        if request.url.path == "/api/v1/chart":
            attempts["chart"] += 1
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(status_code=404, json={"error": {"message": "not found"}})

    transport = httpx.MockTransport(handler)
    with AstroDvishClient(base_url="http://test", transport=transport, max_safe_retries=1) as client:
        health = client.get_health()
        assert health.data.status == "ok"
        with pytest.raises(AstroDvishTimeoutError):
            get_chart_for_bot(
                client,
                ChartRequest(
                    datetime_utc="1984-11-13T11:35:00Z",
                    latitude=53.9006,
                    longitude=27.5590,
                    house_system="P",
                    zodiac_mode="tropical",
                    sidereal_mode=None,
                ),
            )

    assert attempts["health"] == 2
    assert attempts["chart"] == 1

