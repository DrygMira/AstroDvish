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
    assert 'id="tabChartBtn"' in html
    assert 'id="techModeToggleBtn"' in html
    assert 'id="techModeContent" class="hidden"' in html
    assert 'id="techPanelsWrap" class="hidden"' in html


def test_main_wizard_contains_current_data_block() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="wzCurrentDataSummary"' in html
    assert 'id="wzEditDataBtn"' in html


def test_shared_context_sync_and_reset_messages_exist() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "function applySharedContextToForms()" in html
    assert "function syncSharedBirthContext(patch, options = {})" in html
    assert "function applyPlaceSelectionToSharedContext(option, cityQueryValue)" in html
    assert "latitudeDms: Number.isFinite(latitude) ? decimalToDms(latitude, \"lat\") : null" in html
    assert "longitudeDms: Number.isFinite(longitude) ? decimalToDms(longitude, \"lon\") : null" in html
    assert "resetWizardDerivedState();" in html


def test_technical_mode_preserves_modules_and_debug_blocks() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="wzIntervalsList"' in html
    assert 'id="rdHistory"' in html
    assert 'id="reEventsList"' in html
    assert "Raw rectification JSON" in html
    assert 'id="reToggleJsonBtn"' in html
    assert 'id="toggleApiRawBtn"' in html


def test_rect_events_reset_clears_derived_pro_and_comparison_state() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "function resetRectEventsState()" in html
    assert "resetWizardDerivedState();" in html
    assert "Stage 2 и derived Pro/comparison state сброшены." in html


def test_pro_run_payload_preserves_manual_timezone_selection() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "timezone_mode: sharedBirthContext.timezoneMode || timezoneModeEl.value || \"auto\"" in html
    assert "timezone_offset: sharedBirthContext.timezoneMode === \"manual\"" in html
