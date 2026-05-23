from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services.rectification_formula.formula_card_loader import FormulaCardLoader

CONFIRMED_CHILD_BIRTH_DISPLAY_FORMULAS = [
    "Directed ruler_4 -> Natal house_element_5",
    "Directed cusp_10 -> Natal cusp_5",
    "Directed cusp_6 -> Natal Sun",
    "Directed cusp_4 -> Natal Moon",
    "Directed Sun -> Natal Jupiter",
    "Directed cusp_5 -> Natal Chiron",
]


def _build_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SWEPH_EPHE_PATH", str(tmp_path / "ephe"))
    monkeypatch.setenv("SWEPH_AUTO_DOWNLOAD", "false")
    monkeypatch.setenv("APP_LOG_LEVEL", "INFO")
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


def _payload(events_count: int) -> dict:
    events = []
    for idx in range(events_count):
        events.append(
            {
                "event_id": f"ev{idx+1}",
                "event_type": "children_birth",
                "title": f"event {idx+1}",
                "date_text": f"201{idx}-05-12",
                "date_precision": "exact",
                "start_date": f"201{idx}-05-12",
                "end_date": f"201{idx}-05-12",
                "impact_level": 5,
                "reversibility": "irreversible",
                "life_area": "family",
                "sequence_number": idx + 1,
                "notes": "",
                "user_skipped": False,
            }
        )
    return {
        "birth_date_local": "1990-05-12",
        "latitude": 53.9006,
        "longitude": 27.5590,
        "timezone_name": "Europe/Moscow",
        "asc_windows": [
            {
                "start_local": "1990-05-12T14:00:00",
                "end_local": "1990-05-12T14:20:00",
                "sign_name_en": "Libra",
                "sign_name_ru": "Весы",
            }
        ],
        "events": events,
        "settings": {
            "candidate_step_minutes": 5,
            "include_directions": True,
            "include_solars": True,
            "include_lunars": False,
            "include_transits": True,
            "include_totems": False,
        },
    }


def test_rectification_pro_run_endpoint_contract(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=_payload(5))
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "rectification_pro"
    assert body["status"] == "completed"
    assert "candidate_windows" in body
    assert "best_candidates" in body
    assert "method_results" in body
    assert "confidence" in body


def test_rectification_pro_run_endpoint_returns_formula_test_mode_results(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=_payload(2))
    assert response.status_code == 200
    body = response.json()
    assert "formula_test_mode_results" in body
    assert isinstance(body["formula_test_mode_results"], list)
    if body["formula_test_mode_results"]:
        item = body["formula_test_mode_results"][0]
        assert "matched_formula_aspects" in item
        assert "missing_formula_links" in item
        assert "rejected_aspects" in item
        assert "validation_report" in item


def test_rectification_pro_run_low_confidence_for_weak_data(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=_payload(1))
    assert response.status_code == 200
    body = response.json()
    assert body["confidence"]["level"] in {"low", "medium"}


def test_rectification_pro_accepts_new_event_types(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["life_area"] = "family"
    payload["events"][0]["sequence_number"] = 1
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)
    assert response.status_code == 200


def test_rectification_pro_child_birth_expected_by_card_matches_production_card(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    loader = FormulaCardLoader()
    production_card = loader.load_card("RECT_CHILD_BIRTH_001")

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)
    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    expected_rules = result["validation_report"]["expected_by_card"]["direction_rules"]

    assert result["card_id"] == production_card.card_id
    assert result["card_hash"] == production_card.card_hash
    assert result["source_file_path"] == production_card.source_file_path
    assert result["card_version"] == production_card.card_version
    assert [rule["display_formula"] for rule in expected_rules] == CONFIRMED_CHILD_BIRTH_DISPLAY_FORMULAS
    assert expected_rules[0]["aspect_types"] == ["square"]


def test_rectification_pro_uses_symbolic_age_arc_for_formula_test_mode(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["debug"]["direction_method"] == "symbolic_1deg_per_year"


def test_rectification_pro_returns_direction_debug_fields_for_formula_results(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]

    rejected = result["rejected_aspects"]
    assert rejected
    sample = rejected[0]
    assert {
        "directed_point",
        "directed_source_longitude",
        "natal_target",
        "natal_target_longitude",
        "aspect_type",
        "actual_angle",
        "exact_angle",
        "orb",
        "orb_limit",
        "match_status",
        "rejection_reason",
    }.issubset(sample)

    report = result["validation_report"]
    assert report["directed_points_debug"]
    assert report["natal_targets_debug"]
    assert report["rule_debug"]

    checked_pair = report["rule_debug"][0]["checked_pairs"][0]
    assert {
        "directed_point",
        "natal_target",
        "source_coordinate_type",
        "target_coordinate_type",
        "source_natal_coordinate",
        "directed_coordinate",
        "natal_coordinate",
        "actual_angle",
        "exact_angle",
        "orb",
        "orb_limit",
    }.issubset(checked_pair)


def test_rectification_pro_validation_report_table_contains_expert_visible_angles(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["birth_date_local"] = "1978-03-19"
    payload["latitude"] = 40.2341666667
    payload["longitude"] = 69.6947222222
    payload["timezone_name"] = "Asia/Yekaterinburg"
    payload["asc_windows"] = [
        {
            "start_local": "1978-03-19T22:55:00",
            "end_local": "1978-03-19T23:05:00",
            "sign_name_en": "Sagittarius",
            "sign_name_ru": "Стрелец",
        }
    ]
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    table = response.json()["formula_test_mode_results"][0]["validation_report_table"]
    assert "Directed longitude" in table
    assert "Natal longitude" in table
    assert "Actual angle" in table
    assert "Exact angle" in table
    assert "Orb" in table
    assert "Orb limit" in table
    assert "Directed Sun -> Natal Jupiter" in table


def test_rectification_pro_clips_candidates_to_selected_birth_date(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(2)
    payload["birth_date_local"] = "1978-03-19"
    payload["timezone_name"] = "Asia/Yekaterinburg"
    payload["asc_windows"] = [
        {
            "start_local": "1978-03-18T22:09:22",
            "end_local": "1978-03-19T00:41:14",
            "sign_name_en": "Scorpio",
            "sign_name_ru": "Скорпион",
        },
        {
            "start_local": "1978-03-19T22:05:00",
            "end_local": "1978-03-20T00:15:00",
            "sign_name_en": "Scorpio",
            "sign_name_ru": "Скорпион",
        },
    ]
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)
    assert response.status_code == 200
    body = response.json()
    all_candidates = body.get("candidate_windows", [])
    assert all_candidates
    for item in all_candidates:
        ts = item["candidate_time_local"]
        assert ts >= "1978-03-19T00:00:00"
        assert ts < "1978-03-20T00:00:00"
    warnings = body.get("warnings", [])
    assert "candidate_windows_clipped_to_birth_date" in warnings
