from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_stage2_ui_contains_repeat_count_and_sequence_controls() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="reRepeatCountWrap"' in html
    assert 'id="reRepeatCount"' in html
    assert 'id="reSequenceWrap"' in html
    assert 'id="reSequenceNumber"' in html
    assert "repeatable_event_collect_more" in html
