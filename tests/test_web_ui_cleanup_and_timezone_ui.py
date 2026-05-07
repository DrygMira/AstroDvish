from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_main_ui_uses_product_header_without_test_ports_copy() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "AstroDvish — ректификация времени рождения" in html
    assert "Введите данные рождения, пройдите этапы уточнения и проверьте расчётные окна времени." in html
    assert "Тестовая веб-морда астросервиса" not in html
    assert "UI работает на порту 8014" not in html
    assert "API на 8013" not in html


def test_main_ui_hides_api_address_and_keeps_it_in_technical_mode() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="apiBaseUrl"' in html
    assert 'id="wzApiBaseUrl"' in html
    assert '<div class="hidden">' in html
    assert "Технический режим / отдельные модули" in html


def test_timezone_auto_ui_disables_manual_offset_and_shows_auto_resolution() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "timezoneOffsetEl.disabled = isAuto;" in html
    assert "wzTimezoneOffsetEl.disabled = isAuto;" in html
    assert "Рассчитывается автоматически по timezone name." in html
    assert "Используется ручной offset." in html
    assert "Europe/Moscow" in html


def test_timezone_auto_ui_uses_resolved_offset_text_not_stale_manual_value() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "sharedBirthContext.timezoneResolvedOffset" in html
    assert 'ensureSelectDisplayValue(timezoneOffsetEl, resolvedOffset || "auto");' in html
    assert 'ensureSelectDisplayValue(wzTimezoneOffsetEl, resolvedOffset || "auto");' in html


def test_main_ui_has_mobile_safe_birth_seconds_input_and_hint() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="datetimeLocalSeconds"' in html
    assert "Секунды важны для точного Asc/MC. Если неизвестны — оставьте 00." in html
    assert "mobile fallback" in html


def test_main_ui_does_not_truncate_birth_datetime_to_minutes() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "toISOString().slice(0, 16)" not in html
    assert "toISOString().slice(0, 19)" in html
    assert "setDateTimeWithSeconds(nowLocalInputValue(), { syncShared: false });" in html


def test_main_ui_generate_payload_uses_datetime_with_seconds() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "const normalizedDateTime = setDateTimeWithSeconds(datetimeLocalEl.value, { syncShared: false });" in html
    assert "datetime_local: normalizedDateTime," in html


def test_main_ui_sanitizes_openrouter_402_error_text() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Карта рассчитана, но текстовая интерпретация сейчас недоступна. Попробуйте повторить позже." in html
    assert "OpenRouter" not in html
    assert "detail?.raw_error" in html


def test_main_ui_has_generate_technical_debug_fields() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="generateDebugBox"' in html
    assert "normalizeLlmReason" in html
    assert "provider: detail?.provider || null" in html
    assert "requested_max_tokens" in html
    assert "applied_max_tokens" in html
    assert "retried_with_lower_max_tokens" in html


def test_main_ui_deduplicates_llm_unavailable_message_in_status() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data.warnings.filter((item) => item !== "llm_unavailable")' in html


def test_main_ui_has_humanized_openrouter_error_messages_for_common_statuses() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Не удалось авторизоваться в сервисе модели. Обратитесь к администратору." in html
    assert "Сервис модели перегружен. Повторите попытку чуть позже." in html
    assert "Сервис модели временно недоступен. Попробуйте ещё раз позже." in html


def test_main_ui_supports_humanized_geocode_error_and_technical_debug() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "detail?.user_message" in html
    assert 'id="geocodeDebugBox"' in html
