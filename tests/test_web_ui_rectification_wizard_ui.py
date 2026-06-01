from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_bundle import get_main_ui_bundle
import web_ui.main as web_ui_main


def test_rectification_wizard_tab_and_progress_exist() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)
    assert response.status_code == 200
    assert "Ректификация рождения" in html
    assert "Шаг 1 из 5" in html
    assert "Шаг 5 из 5" in html
    assert 'id="wzProgressText"' in html


def test_stage1_main_ui_hides_token_debug_strings_and_has_human_fallback_text() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)
    assert response.status_code == 200
    assert "Токены: input=" not in html
    assert "Ответ модели не получен, поэтому использован резервный расчёт по вашим ответам." in html
    assert "Резервный режим:" not in html


def test_stage1_main_ui_has_explanation_and_secondary_intervals_helpers() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)
    assert response.status_code == 200
    assert "Почему выбран кандидат" in html
    assert "formatStage1SecondaryCandidatesHtml" in html
    assert "time_ranges_local" in html


def test_stage2_ui_has_sequence_number_control() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)
    assert response.status_code == 200
    assert 'id="reSequenceWrap"' in html
    assert 'id="reSequenceNumber"' in html
    assert "Какой это случай по счёту?" in html


def test_stage2_pro_e2e_helpers_present_in_ui() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)
    assert response.status_code == 200
    assert 'id="reAddTestEventsBtn"' in html
    assert "normalizeProEventCard" in html
    assert "buildProTestEventsPreset" in html
    assert "sequence_number" in html


def test_stage2_ui_human_cards_without_raw_field_labels() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)
    assert response.status_code == 200
    assert "<div>date_text:" not in html
    assert "<div>life_area:" not in html
    assert "<div>reversibility:" not in html
    assert "Сила воздействия" in html
    assert "Сфера:" in html
