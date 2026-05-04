from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_shared_birth_context_exists_with_required_fields() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "const sharedBirthContext = {" in html
    assert "apiBaseUrl:" in html
    assert "birthDateLocal:" in html
    assert "birthDateTimeLocal:" in html
    assert "selectedPlaceLabel:" in html
    assert "timezoneSource:" in html
    assert "aspectOrbProfile:" in html


def test_main_ui_has_two_primary_tabs_and_technical_mode_accordion() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="tabWizardBtn"' in html
    assert 'id="tabChartBtn"' in html
    assert "Обычный расчёт карты" in html
    assert 'id="techModeToggleBtn"' in html
    assert "Технический режим / отдельные модули" in html
    assert 'id="techModeContent" class="hidden"' in html
    assert 'id="techPanelsWrap" class="hidden"' in html


def test_main_wizard_contains_current_data_block() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Текущие данные" in html
    assert 'id="wzCurrentDataSummary"' in html
    assert "Изменить данные" in html


def test_shared_context_sync_and_reset_messages_exist() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "function applySharedContextToForms()" in html
    assert "function syncSharedBirthContext(patch, options = {})" in html
    assert "function applyPlaceSelectionToSharedContext(option, cityQueryValue)" in html
    assert "Вы изменили данные рождения. Предыдущие интервалы, диалог и Pro-ректификация будут сброшены." in html


def test_technical_mode_preserves_modules_and_debug_blocks() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Asc-интервалы" in html
    assert "Диалог по Asc" in html
    assert "События жизни" in html
    assert "Raw rectification JSON" in html
    assert "Показать технический JSON" in html
    assert "Показать ответ API целиком" in html
