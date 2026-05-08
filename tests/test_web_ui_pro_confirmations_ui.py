from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_pro_ui_renders_human_confirmations_instead_of_raw_entries_summary() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "renderProConfirmations" in html
    assert "extractProMatchDetails" in html
    assert "Технически подтверждено сигналом метода, требуется экспертная проверка" in html
    assert "entries=" not in html
    assert "matched_events=" not in html


def test_pro_ui_keeps_technical_json_available() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'id="rpRawBox"' in html
    assert "rpRawBoxEl.textContent = JSON.stringify(data, null, 2);" in html


def test_pro_ui_contains_window_width_explanation_text() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Ширина окна:" in html
    assert "Это не точное время рождения." in html


def test_pro_ui_contains_source_interval_and_clipping_explanation() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Источник Asc-интервала:" in html
    assert "Окно было ограничено границами выбранной даты рождения." in html
