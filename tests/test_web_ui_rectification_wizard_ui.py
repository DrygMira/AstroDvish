from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_rectification_wizard_tab_and_progress_exist() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Ректификация рождения" in html
    assert "Ректификация рождения — мастер-сценарий" in html
    assert "Шаг 1 из 5 — Дата и место" in html
    assert "Шаг 5 из 5 — Pro-ректификация" in html
    assert 'id="wzProgressText"' in html


def test_rectification_wizard_stage2_context_and_guard_texts_exist() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Контекст ректификации:" in html
    assert "Собрано событий: ${eventsCount} / желательно 5–7" in html
    assert "Сначала завершите диалог по Asc и сбор событий жизни." in html


def test_rectification_wizard_state_reset_and_pro_windows_builder_exist() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "const rectificationWizardState = {" in html
    assert "buildProAscWindowsFromStage1" in html
    assert "time_ranges_local" in html
    assert "Вы изменили данные рождения. Предыдущие интервалы, диалог и Pro-ректификация будут сброшены." in html


def test_stage1_main_ui_hides_token_debug_strings_and_shows_human_fallback_text() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Токены: input=" not in html
    assert "Ответ модели не получен, поэтому использован резервный расчёт по вашим ответам." in html


def test_stage2_pro_e2e_helpers_present_in_ui() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="reAddTestEventsBtn"' in html
    assert "Добавить тестовые события для Pro" in html
    assert "normalizeProEventCard" in html
    assert "buildProTestEventsPreset" in html
    assert "Недостаточно данных для Pro-ректификации" in html
