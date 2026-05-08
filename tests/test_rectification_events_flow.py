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


def _answer(
    question: dict,
    *,
    idx: int,
    skipped: bool = False,
    impact_level: int | None = None,
    repeat_count: int | None = None,
    sequence_number: int | None = 1,
) -> dict:
    return {
        "question_id": question["question_id"],
        "event_type": question["event_type"],
        "title": "" if skipped else f"major event {idx}",
        "date_text": "" if skipped else f"201{idx}-0{(idx % 9) + 1}",
        "impact_level": impact_level,
        "reversibility": None,
        "life_area": None,
        "repeat_count": repeat_count,
        "sequence_number": sequence_number,
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


def test_repeatable_event_requires_sequence_number(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        start = client.post("/api/v1/rectification/events/start", json={}).json()
        assert start["question"]["event_type"] == "child_birth"
        cont = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": start["dialog_history"],
                "last_answer": _answer(start["question"], idx=1, sequence_number=None),
            },
        )
    assert cont.status_code == 200
    body = cont.json()
    assert body["status"] == "ask_question"
    assert "sequence_number_required_retry" in body["warnings"]


def test_child_birth_sequence_1_and_2_are_valid(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        state = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": state["dialog_history"],
                "last_answer": _answer(state["question"], idx=1, sequence_number=1),
            },
        ).json()

        state = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": state["dialog_history"],
                "last_answer": _answer(state["question"], idx=2, sequence_number=2),
            },
        ).json()

        final = client.post(
            "/api/v1/rectification/events/finalize",
            json={"dialog_history": state["dialog_history"]},
        ).json()

    events = [event for event in final["events"] if event["event_type"] == "child_birth"]
    assert events
    assert events[0]["sequence_number"] == 1


def test_repeatable_count_first_flow_collects_declared_repeats(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        assert state["question"]["event_type"] == "child_birth"
        state = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": state["dialog_history"],
                "last_answer": _answer(
                    state["question"],
                    idx=1,
                    repeat_count=2,
                    sequence_number=1,
                ),
            },
        ).json()
        assert state["status"] == "ask_question"
        assert state["question"]["event_type"] == "child_birth"
        assert "repeatable_event_collect_more" in state["warnings"]

        state = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": state["dialog_history"],
                "last_answer": _answer(
                    state["question"],
                    idx=2,
                    repeat_count=2,
                    sequence_number=2,
                ),
            },
        ).json()
        assert state["status"] == "ask_question"
        assert state["question"]["event_type"] == "marriage_start"

        final = client.post(
            "/api/v1/rectification/events/finalize",
            json={"dialog_history": state["dialog_history"]},
        ).json()

    child_events = [event for event in final["events"] if event["event_type"] == "child_birth"]
    assert len(child_events) == 2
    assert {event["sequence_number"] for event in child_events} == {1, 2}


def test_marriage_and_divorce_are_separate_event_types(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        sequence = []
        for idx in range(3):
            sequence.append(state["question"]["event_type"])
            state = client.post(
                "/api/v1/rectification/events/continue",
                json={
                    "dialog_history": state["dialog_history"],
                    "last_answer": _answer(state["question"], idx=idx + 1, sequence_number=1),
                },
            ).json()
    assert "marriage_start" in sequence
    assert "divorce_separation" in sequence


def test_death_question_metadata_one_time_vs_repeatable(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    questions: list[dict] = []
    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        questions.append(state["question"])
        for idx in range(10):
            state = client.post(
                "/api/v1/rectification/events/continue",
                json={
                    "dialog_history": state["dialog_history"],
                    "last_answer": _answer(state["question"], idx=idx + 1, sequence_number=1),
                },
            ).json()
            if state.get("status") != "ask_question":
                break
            questions.append(state["question"])
    q_map = {q["event_type"]: q for q in questions}
    assert q_map["death_father"]["repeatable"] is False
    assert q_map["death_mother"]["repeatable"] is False
    assert q_map["death_sibling"]["repeatable"] is True
    assert q_map["death_grandparent"]["repeatable"] is True
    assert q_map["death_sibling"]["requires_sequence_number"] is True


def test_repeatable_relocation_supports_multiple_entries(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        state = client.post("/api/v1/rectification/events/start", json={}).json()
        safety = 0
        while state.get("status") == "ask_question" and state["question"]["event_type"] != "local_relocation":
            safety += 1
            if safety > 20:
                raise AssertionError("Could not reach local_relocation question in Stage 2 flow")
            state = client.post(
                "/api/v1/rectification/events/continue",
                json={
                    "dialog_history": state["dialog_history"],
                    "last_answer": _answer(state["question"], idx=safety, skipped=True, sequence_number=None),
                },
            ).json()

        assert state["question"]["event_type"] == "local_relocation"
        state = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": state["dialog_history"],
                "last_answer": _answer(state["question"], idx=1, repeat_count=2, sequence_number=1),
            },
        ).json()
        assert state["question"]["event_type"] == "local_relocation"

        state = client.post(
            "/api/v1/rectification/events/continue",
            json={
                "dialog_history": state["dialog_history"],
                "last_answer": _answer(state["question"], idx=2, repeat_count=2, sequence_number=2),
            },
        ).json()
        assert state["status"] == "ask_question"
        assert state["question"]["event_type"] != "local_relocation"


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
                    "sequence_number": 1,
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
                "last_answer": _answer(start["question"], idx=1, skipped=True, sequence_number=None),
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
