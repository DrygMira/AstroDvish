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
    assert "Рассчитывается автоматически по timezone name" in html
    assert "Используется ручной offset" in html
    assert "Europe/Moscow" in html


def test_timezone_auto_ui_uses_resolved_offset_text_not_stale_manual_value() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "sharedBirthContext.timezoneResolvedOffset" in html
    assert "auto" in html
