from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


class _FakeOpenAIResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


def _set_openai_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL_GENERATE", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_MODEL_STAGE1", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_MODEL_PRO", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_MAX_TOKENS_GENERATE", "8000")
    monkeypatch.setenv("OPENAI_MAX_TOKENS_STAGE1", "3000")
    monkeypatch.setenv("OPENAI_MAX_TOKENS_PRO", "12000")


def test_llm_provider_openai_uses_openai_client(monkeypatch) -> None:
    _set_openai_env(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeOpenAIResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeOpenAIResponse()

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    result = web_ui_main._call_llm_chat(
        system_prompt="sys",
        user_prompt="usr",
        request_kind=web_ui_main.OPENROUTER_REQUEST_KIND_GENERATE,
        route_label="/api/generate",
    )

    assert "api.openai.com/v1/chat/completions" in captured["url"]
    assert "openrouter.ai" not in captured["url"]
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-5.4-mini"
    assert "test-openai-key" not in str(result)


def test_generate_does_not_use_openrouter_when_provider_openai(monkeypatch) -> None:
    _set_openai_env(monkeypatch)

    class _FakeChartResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "objects": {
                    "sun": {"sign_name_en": "Aries", "sign_name_ru": "Овен", "sign_degree": 10.0, "absolute_degree_0_360": 10.0},
                    "moon": {"sign_name_en": "Cancer", "sign_name_ru": "Рак", "sign_degree": 5.0, "absolute_degree_0_360": 95.0},
                },
                "angles": {"asc": 12.5, "mc": 220.0},
                "houses": {"house_system": "P", "cusp_details": {}},
                "aspects": [],
                "meta": {},
            }

    def fake_post_to_api_with_fallback(*, base_url: str, path: str, payload: dict[str, Any], timeout: int) -> _FakeChartResponse:
        return _FakeChartResponse()

    def fail_if_openrouter_called(*args, **kwargs):
        raise AssertionError("OpenRouter call should not be used when LLM_PROVIDER=openai")

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post_to_api_with_fallback)
    monkeypatch.setattr(web_ui_main, "_call_openrouter_chat", fail_if_openrouter_called)
    monkeypatch.setattr(web_ui_main.httpx, "post", lambda *args, **kwargs: _FakeOpenAIResponse())

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
    assert data["llm_status"] == "ok"
    assert isinstance(data["horoscope_text"], str) and data["horoscope_text"]
    assert data["llm_debug"]["provider"] == "openai"
