from __future__ import annotations

from typing import Any

import pytest

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
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_MODEL_RECTIFICATION", "openai/gpt-4.1")
    monkeypatch.setenv("OPENROUTER_MODEL_HOROSCOPE", "openai/gpt-4.1")
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
    assert detail["model"] == "openai/gpt-4.1"
    assert detail["route"] == "unknown"
    assert detail["requested_max_tokens"] == 8000
    assert detail["applied_max_tokens"] == 8000
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
