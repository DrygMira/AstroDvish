from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


class _FakeOpenRouterResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        self.text = text or ""

    def json(self) -> dict[str, Any]:
        return self._payload


def _set_openrouter_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY_BACKUP_1", "test-key-backup-1")
    monkeypatch.setenv("OPENROUTER_API_KEY_BACKUP_2", "test-key-backup-2")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_MODEL_RECTIFICATION", "openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_MODEL_HOROSCOPE", "openai/gpt-4.1")
    monkeypatch.setenv("LLM_MODEL_GENERATE_PRIMARY", "openai/gpt-4.1")
    monkeypatch.setenv("LLM_MODEL_GENERATE_FALLBACK", "openai/gpt-4.1-mini")
    monkeypatch.setenv("LLM_MODEL_STAGE1_PRIMARY", "openai/gpt-4.1-mini")
    monkeypatch.setenv("LLM_MODEL_STAGE1_FALLBACK", "openai/gpt-4.1-mini")
    monkeypatch.setenv("LLM_MODEL_PRO_PRIMARY", "openai/gpt-4.1")
    monkeypatch.setenv("LLM_MODEL_PRO_FALLBACK", "openai/gpt-4.1-mini")
    monkeypatch.setenv("MAX_LLM_ATTEMPTS", "4")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS_DEFAULT", "6000")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS_STAGE1", "2000")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS_GENERATE", "8000")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS_PRO", "12000")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS_HARD_LIMIT", "20000")


def test_openrouter_max_tokens_hard_limit_clamps_requested_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_openrouter_env(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeOpenRouterResponse()

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    result = web_ui_main._call_openrouter_chat(
        system_prompt="system",
        user_prompt="user",
        request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_PRO,
        requested_max_tokens=65536,
    )

    assert captured["json"]["max_tokens"] == 20000
    assert result["requested_max_tokens"] == 65536
    assert result["applied_max_tokens"] == 20000


@pytest.mark.parametrize(
    ("request_kind", "expected_max_tokens"),
    [
        (web_ui_main.OPENROUTER_REQUEST_KIND_STAGE1, 2000),
        (web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE, 8000),
        (web_ui_main.OPENROUTER_REQUEST_KIND_PRO, 12000),
    ],
)
def test_openrouter_uses_configured_max_tokens_by_request_kind(
    monkeypatch: pytest.MonkeyPatch,
    request_kind: str,
    expected_max_tokens: int,
) -> None:
    _set_openrouter_env(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        captured["json"] = json
        return _FakeOpenRouterResponse()

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    result = web_ui_main._call_openrouter_chat(
        system_prompt="system",
        user_prompt="user",
        request_kind=request_kind,
    )

    assert captured["json"]["max_tokens"] == expected_max_tokens
    assert result["requested_max_tokens"] == expected_max_tokens
    assert result["applied_max_tokens"] == expected_max_tokens


def test_openrouter_non_200_includes_token_debug_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_openrouter_env(monkeypatch)

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        return _FakeOpenRouterResponse(
            status_code=402,
            payload={"error": {"message": "This request requires more credits, or fewer max_tokens."}},
            text='{"error":{"message":"This request requires more credits, or fewer max_tokens."}}',
        )

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    with pytest.raises(web_ui_main.HTTPException) as exc_info:
        web_ui_main._call_openrouter_chat(
            system_prompt="system",
            user_prompt="user",
            request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE,
        )

    detail = exc_info.value.detail
    assert detail["status_code"] == 402
    assert detail["reason"] == "insufficient_credits_or_max_tokens"
    assert detail["model"] == "openai/gpt-4.1-mini"
    assert detail["route"] == "unknown"
    assert detail["requested_max_tokens"] == 8000
    assert detail["applied_max_tokens"] == 4000
    assert detail["first_applied_max_tokens"] == 8000
    assert detail["retried_with_lower_max_tokens"] is True
    assert isinstance(detail["attempts"], list)
    assert detail["attempts"][0]["key_name"] == "primary"
    assert "credits" in detail["raw_error"]


def test_openrouter_generate_retries_with_affordable_tokens_on_402(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_openrouter_env(monkeypatch)
    sent_max_tokens: list[int] = []

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        sent_max_tokens.append(int(json["max_tokens"]))
        if len(sent_max_tokens) == 1:
            return _FakeOpenRouterResponse(
                status_code=402,
                payload={"error": {"message": "This request requires more credits, or fewer max_tokens."}},
                text='{"error":{"message":"This request requires more credits, or fewer max_tokens. You requested up to 8000 tokens, but can only afford 2218."}}',
            )
        return _FakeOpenRouterResponse()

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    result = web_ui_main._call_openrouter_chat(
        system_prompt="system",
        user_prompt="user",
        request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE,
        route_label="/api/generate",
        retry_on_affordable_402=True,
    )

    assert sent_max_tokens == [8000, 2218]
    assert result["requested_max_tokens"] == 8000
    assert result["first_applied_max_tokens"] == 8000
    assert result["applied_max_tokens"] == 2218
    assert result["retried_with_lower_max_tokens"] is True
    assert result["route"] == "/api/generate"


def test_compact_llm_chart_context_reduces_payload_shape() -> None:
    chart = {
        "objects": {
            "sun": {
                "sign_name_en": "Aries",
                "sign_name_ru": "Овен",
                "sign_degree": 12.3,
                "absolute_degree_0_360": 12.3,
                "house": 1,
                "retrograde": False,
                "speed": 1.0,
                "extra_large_field": "x" * 5000,
            }
        },
        "angles": {"asc": 10.5, "mc": 200.1},
        "houses": {"house_system": "P", "cusp_details": {"1": {"sign_name_en": "Aries", "sign_degree": 10.5}}},
        "aspects": [{"object_a": "sun", "object_b": "moon", "aspect_type": "trine", "orb": 0.5}],
        "meta": {"foo": "bar"},
        "verbose_unneeded": {"blob": "y" * 7000},
    }

    compact = web_ui_main._compact_llm_chart_context(chart)
    assert "verbose_unneeded" not in compact
    assert compact["objects"]["sun"]["sign_name_en"] == "Aries"
    assert "extra_large_field" not in compact["objects"]["sun"]
    assert compact["angles"]["asc"] == 10.5
    assert compact["houses"]["house_system"] == "P"
    assert compact["aspects"][0]["aspect_type"] == "trine"


def test_truncate_prompt_text_applies_limit() -> None:
    long_text = "a" * 2500
    truncated = web_ui_main._truncate_prompt_text(long_text, max_chars=2000)
    assert len(truncated) < len(long_text)
    assert "[Промт сокращён" in truncated


def test_generate_returns_fallback_text_when_llm_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeChartResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "objects": {
                    "sun": {
                        "sign_name_ru": "Овен",
                        "sign_name_en": "Aries",
                        "sign_degree": 10.0,
                        "absolute_degree_0_360": 10.0,
                        "house": 1,
                        "retrograde": False,
                        "speed": 1.0,
                    },
                    "moon": {
                        "sign_name_ru": "Рак",
                        "sign_name_en": "Cancer",
                        "sign_degree": 5.0,
                        "absolute_degree_0_360": 95.0,
                        "house": 4,
                        "retrograde": False,
                        "speed": 12.0,
                    },
                },
                "angles": {"asc": 12.5, "mc": 220.0},
                "houses": {"house_system": "P", "cusp_details": {}},
                "aspects": [],
                "meta": {},
            }

    def fake_post_to_api_with_fallback(*, base_url: str, path: str, payload: dict[str, Any], timeout: int) -> _FakeChartResponse:
        return _FakeChartResponse()

    def fake_render_horoscope_via_openai(prompt_text: str, chart: dict[str, Any], core_identity: dict[str, Any]) -> str:
        raise web_ui_main.HTTPException(
            status_code=502,
            detail={
                "message": "OpenRouter returned non-200 status",
                "status_code": 402,
                "reason": "insufficient_credits_or_max_tokens",
                "model": "openai/gpt-4.1",
                "requested_max_tokens": 8000,
                "applied_max_tokens": 400,
            },
        )

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post_to_api_with_fallback)
    monkeypatch.setattr(web_ui_main, "_render_horoscope_via_openai", fake_render_horoscope_via_openai)

    payload = {
        "api_base_url": "http://127.0.0.1:8013",
        "datetime_local": "1990-05-12T14:35:00",
        "timezone_mode": "auto",
        "timezone_offset": "+03:00",
        "timezone_name": "Europe/Moscow",
        "latitude": 55.7558,
        "longitude": 37.6173,
        "house_system": "P",
        "aspect_orb_profile": "avestan",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
        "prompt_text": "Сделай гороскоп по этим данным.",
    }

    with TestClient(web_ui_main.app) as client:
        response = client.post("/api/generate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["chart_status"] == "ok"
    assert data["llm_status"] == "unavailable"
    assert data["horoscope_text"] is None
    assert "Попробуйте повторить позже" in data["llm_message"]
    assert "llm_unavailable" in data["warnings"]
    assert data["llm_debug"]["status_code"] == 402
    assert data["llm_debug"]["reason"] == "insufficient_credits_or_max_tokens"


def test_openrouter_default_model_is_gpt41_when_env_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL_GENERATE_PRIMARY", raising=False)
    monkeypatch.delenv("LLM_MODEL_PRO_PRIMARY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    settings = web_ui_main._load_openrouter_settings()
    assert settings["model"] == "openai/gpt-4.1"
    assert settings["models_by_scenario"][web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE]["primary"] == "openai/gpt-4.1"
    assert settings["models_by_scenario"][web_ui_main.OPENROUTER_REQUEST_KIND_PRO]["primary"] == "openai/gpt-4.1"


def test_openrouter_cascade_uses_fallback_model_after_primary_402(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_openrouter_env(monkeypatch)
    seen_models: list[str] = []

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        seen_models.append(str(json["model"]))
        if len(seen_models) == 1:
            return _FakeOpenRouterResponse(
                status_code=402,
                payload={"error": {"message": "credits"}},
                text='{"error":{"message":"This request requires more credits, or fewer max_tokens. You requested up to 8000 tokens, but can only afford 1200."}}',
            )
        return _FakeOpenRouterResponse()

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    result = web_ui_main._call_openrouter_chat(
        system_prompt="system",
        user_prompt="user",
        request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE,
    )
    assert seen_models == ["openai/gpt-4.1", "openai/gpt-4.1-mini"]
    assert result["fallback_used"] is True
    assert result["final_source"] == "llm_fallback"
    assert result["attempts"][0]["status_code"] == 402
    assert result["attempts"][1]["status_code"] == 200


def test_openrouter_cascade_uses_backup_key_after_primary_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_openrouter_env(monkeypatch)
    auth_headers: list[str] = []

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        auth_headers.append(headers["Authorization"])
        if len(auth_headers) <= 2:
            return _FakeOpenRouterResponse(
                status_code=401,
                payload={"error": {"message": "unauthorized"}},
                text='{"error":{"message":"unauthorized"}}',
            )
        return _FakeOpenRouterResponse()

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    result = web_ui_main._call_openrouter_chat(
        system_prompt="system",
        user_prompt="user",
        request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE,
    )
    assert auth_headers[0] == "Bearer test-key"
    assert auth_headers[1] == "Bearer test-key"
    assert auth_headers[2] == "Bearer test-key-backup-1"
    assert result["key_name"] == "backup_1"
    assert result["fallback_used"] is True


def test_openrouter_cascade_exhaustion_returns_template_fallback_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_openrouter_env(monkeypatch)

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        return _FakeOpenRouterResponse(
            status_code=503,
            payload={"error": {"message": "provider unavailable"}},
            text='{"error":{"message":"provider unavailable"}}',
        )

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    with pytest.raises(web_ui_main.HTTPException) as exc_info:
        web_ui_main._call_openrouter_chat(
            system_prompt="system",
            user_prompt="user",
            request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE,
        )
    detail = exc_info.value.detail
    assert detail["final_source"] == "template_fallback"
    assert detail["fallback_used"] is True
    assert len(detail["attempts"]) == 4
    serialized = str(detail)
    assert "test-key-backup-1" not in serialized
    assert "test-key-backup-2" not in serialized
    assert "test-key" not in serialized


def test_scenario_specific_model_env_has_priority_over_openrouter_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_openrouter_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/legacy-model")
    monkeypatch.setenv("LLM_MODEL_GENERATE_PRIMARY", "openai/priority-model")

    captured_models: list[str] = []

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenRouterResponse:
        captured_models.append(str(json["model"]))
        return _FakeOpenRouterResponse()

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    web_ui_main._call_openrouter_chat(
        system_prompt="system",
        user_prompt="user",
        request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE,
    )
    assert captured_models[0] == "openai/priority-model"
