from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _build_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SWEPH_EPHE_PATH", str(tmp_path / "ephe"))
    monkeypatch.setenv("SWEPH_AUTO_DOWNLOAD", "false")
    monkeypatch.setenv("APP_LOG_LEVEL", "INFO")
    get_settings.cache_clear()
    return TestClient(create_app())


def _answer(question: dict, *, idx: int, skipped: bool = False, impact_level: int | None = None) -> dict:
    return {
        "question_id": question["question_id"],
        "event_type": question["event_type"],
        "title": "" if skipped else f"major event {idx}",
        "date_text": "" if skipped else f"201{idx}-0{(idx % 9) + 1}",
        "impact_level": impact_level,
        "reversibility": None,
        "life_area": None,
        "notes": "" if skipped else "raw user note",
        "user_skipped": skipped,
    }


def test_events_start_flow(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    with client:
        response = client.post("/api/v1/rectification/events/start", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ask_question"
    assert body["step_index"] == 1
    assert body["events_collected_count"] == 0
    assert body["question"]["question_id"]
    assert body["question"]["options"]


def test_events_continue_flow(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    with client:
        start = client.post("/api/v1/rectification/events/start", json={}).json()
        payload = {
            "dialog_history": start["dialog_history"],
            "last_answer": _answer(start["question"], idx=1),
        }
        cont = client.post("/api/v1/rectification/events/continue", json=payload)

    assert cont.status_code == 200
    body = cont.json()
    assert body["status"] == "ask_question"
    assert body["events_collected_count"] == 1
    assert body["step_index"] == 2


def test_events_finalize_with_3_events_low_confidence(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        for idx in range(1, 4):
            state = client.post(
                "/api/v1/rectification/events/continue",
                json={
                    "dialog_history": state["dialog_history"],
                    "last_answer": _answer(state["question"], idx=idx, impact_level=4),
                },
            ).json()

        final = client.post(
            "/api/v1/rectification/events/finalize",
            json={"dialog_history": state["dialog_history"]},
        )

    assert final.status_code == 200
    body = final.json()
    assert body["status"] == "finalized"
    assert body["events_count"] == 3
    assert body["confidence_preliminary"] == "low"
    assert body["strong_events_count"] == 3


def test_events_finalize_with_7_events(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        for idx in range(1, 8):
            state = client.post(
                "/api/v1/rectification/events/continue",
                json={
                    "dialog_history": state["dialog_history"],
                    "last_answer": _answer(state["question"], idx=idx, impact_level=5 if idx % 2 == 0 else 3),
                },
            ).json()

        final = client.post(
            "/api/v1/rectification/events/finalize",
            json={"dialog_history": state["dialog_history"]},
        )

    assert final.status_code == 200
    body = final.json()
    assert body["events_count"] == 7
    assert body["confidence_preliminary"] == "medium"
    assert body["strong_events_count"] >= 3


def test_events_empty_answer_retry(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    with client:
        start = client.post("/api/v1/rectification/events/start", json={}).json()
        cont = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": start["dialog_history"],
                "last_answer": {
                    "question_id": start["question"]["question_id"],
                    "event_type": start["question"]["event_type"],
                    "title": "",
                    "date_text": "",
                    "impact_level": None,
                    "notes": "",
                    "user_skipped": False,
                },
            },
        )

    assert cont.status_code == 200
    body = cont.json()
    assert body["status"] == "ask_question"
    assert "empty_answer_retry" in body["warnings"]


def test_events_skip_scenario(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    with client:
        start = client.post("/api/v1/rectification/events/start", json={}).json()
        cont = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": start["dialog_history"],
                "last_answer": _answer(start["question"], idx=1, skipped=True),
            },
        )

    assert cont.status_code == 200
    body = cont.json()
    assert body["status"] == "ask_question"
    assert body["events_collected_count"] == 0


def test_events_json_and_impact_range(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        for idx in range(1, 4):
            state = client.post(
                "/api/v1/rectification/events/continue",
                json={
                    "dialog_history": state["dialog_history"],
                    "last_answer": _answer(state["question"], idx=idx),
                },
            ).json()

        final = client.post(
            "/api/v1/rectification/events/finalize",
            json={"dialog_history": state["dialog_history"]},
        ).json()

    assert final["status"] == "finalized"
    assert isinstance(final["events"], list)
    for event in final["events"]:
        assert event["event_id"]
        assert 1 <= event["impact_level"] <= 5
        assert event["date_precision"] in {"exact", "month", "year", "range", "unknown"}
