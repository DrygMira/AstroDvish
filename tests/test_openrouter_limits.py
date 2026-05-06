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
