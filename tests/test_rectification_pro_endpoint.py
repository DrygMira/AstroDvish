from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services.rectification_formula.formula_card_loader import FormulaCardLoader
from app.services.rectification_pro.formula_refinement_service import FormulaRefinementService

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


def _four_children_payload() -> dict:
    return {
        "birth_date_local": "1978-03-19",
        "latitude": 40.234167,
        "longitude": 69.694722,
        "timezone_name": "Etc/GMT-5",
        "timezone_mode": "manual",
        "timezone_offset": "+05:00",
        "asc_windows": [
            {
                "start_local": "1978-03-19T22:55:00",
                "end_local": "1978-03-19T23:01:00",
                "sign_name_en": "Scorpio",
                "sign_name_ru": "Scorpio",
            }
        ],
        "events": [
            {
                "event_id": "ev1",
                "event_type": "child_birth",
                "title": "child 1",
                "date_text": "2000-01-01",
                "date_precision": "exact",
                "start_date": "2000-01-01",
                "end_date": "2000-01-01",
                "impact_level": 5,
                "reversibility": "irreversible",
                "life_area": "family",
                "sequence_number": 1,
                "notes": "",
                "user_skipped": False,
            },
            {
                "event_id": "ev2",
                "event_type": "child_birth",
                "title": "child 2",
                "date_text": "2002-02-02",
                "date_precision": "exact",
                "start_date": "2002-02-02",
                "end_date": "2002-02-02",
                "impact_level": 5,
                "reversibility": "irreversible",
                "life_area": "family",
                "sequence_number": 2,
                "notes": "",
                "user_skipped": False,
            },
            {
                "event_id": "ev3",
                "event_type": "child_birth",
                "title": "child 3",
                "date_text": "2004-03-03",
                "date_precision": "exact",
                "start_date": "2004-03-03",
                "end_date": "2004-03-03",
                "impact_level": 5,
                "reversibility": "irreversible",
                "life_area": "family",
                "sequence_number": 3,
                "notes": "",
                "user_skipped": False,
            },
            {
                "event_id": "ev4",
                "event_type": "child_birth",
                "title": "child 4",
                "date_text": "2005-11-07",
                "date_precision": "exact",
                "start_date": "2005-11-07",
                "end_date": "2005-11-07",
                "impact_level": 5,
                "reversibility": "irreversible",
                "life_area": "family",
                "sequence_number": 4,
                "notes": "",
                "user_skipped": False,
            },
        ],
        "settings": {
            "candidate_step_minutes": 1,
            "formula_refinement_step_seconds": 30,
            "include_directions": True,
            "include_solars": True,
            "include_lunars": False,
            "include_transits": True,
            "include_totems": False,
            "formula_card_id": "RECT_CHILD_BIRTH_001",
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


def test_rectification_pro_run_endpoint_returns_formula_refinement_results(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "formula_refinement_results" in body
    refinement = body["formula_refinement_results"]
    assert refinement["enabled"] is True
    assert refinement["direction_method"] == "symbolic_1deg_per_year"
    assert refinement["supported_step_seconds"] == [300, 60, 30, 10]
    assert "best_candidate" in refinement
    assert "top_candidates" in refinement


def test_rectification_pro_handles_four_child_birth_events_and_exposes_performance_debug(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _four_children_payload()
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "formula_refinement_results" in body
    refinement = body["formula_refinement_results"]
    assert refinement["card_id"] == "RECT_CHILD_BIRTH_001"
    performance = body["performance_debug"]
    assert performance["event_count"] == 4
    assert performance["candidate_count"] >= 1
    assert performance["formula_count"] >= 1
    assert performance["card_id"] == "RECT_CHILD_BIRTH_001"
    assert performance["total_runtime_ms"] >= 0
    assert performance["slowest_stage"] in performance["stage_timings_ms"]
    assert "coarse_candidate" in refinement
    assert "working_time_ranges" in refinement
    assert "working_time_range" in refinement
    assert "card_id" in refinement


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
    assert expected_rules[0]["formula"] == "Directed ruler_4 -> Natal house_element_5"
    assert expected_rules[0]["source_layer"] == "directed"
    assert expected_rules[0]["target_layer"] == "natal"
    assert expected_rules[0]["priority"] == "golden"
    assert expected_rules[0]["role"] == "event_confirmation"
    assert expected_rules[0]["orb_limit"] == 1.0
    assert expected_rules[0]["meaning"]
    assert expected_rules[1]["aspect"] == "opposition"
    assert expected_rules[1]["aspect_types"] == ["opposition"]
    assert expected_rules[3]["aspect"] == "trine"
    assert expected_rules[3]["aspect_types"] == ["trine"]


def test_rectification_pro_child_birth_cusp_10_to_cusp_5_is_opposition_and_over_orb(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    expected_rules = result["validation_report"]["expected_by_card"]["direction_rules"]
    cusp_rule = next(rule for rule in expected_rules if rule["id"] == "cusp_10_to_cusp_5")
    assert cusp_rule["aspect"] == "opposition"
    assert cusp_rule["aspect_types"] == ["opposition"]

    rejected = next(item for item in result["rejected_aspects"] if item["formula_rule_matched"] == "cusp_10_to_cusp_5")
    assert rejected["aspect_type"] == "opposition"
    assert rejected["rejection_reason"] == "over_orb"

    missed = next(item for item in result["missing_formula_links"] if item["rule_id"] == "cusp_10_to_cusp_5")
    assert missed["reason"] == "over_orb_only"


def test_rectification_pro_can_select_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["settings"]["formula_card_id"] = "RECT_CHILD_BIRTH_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_CHILD_BIRTH_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 94
    assert result["priority_counts"] == {
        "golden": 24,
        "supporting": 39,
        "context": 31,
        "ambiguity_risk": 0,
    }
    refinement = body["formula_refinement_results"]
    assert refinement["card_id"] == "RECT_CHILD_BIRTH_002_DRAFT"
    assert "formula_test_mode_results" not in (refinement["best_candidate"] or {})
    assert refinement["top_candidates"]
    assert "formula_test_mode_results" not in refinement["top_candidates"][0]
    assert "chart_response" not in refinement["top_candidates"][0]


def test_rectification_pro_can_select_profession_change_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "profession_change"
    payload["settings"]["formula_card_id"] = "RECT_PROFESSION_CHANGE_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_PROFESSION_CHANGE_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 106
    assert result["priority_counts"] == {
        "golden": 34,
        "supporting": 46,
        "context": 26,
        "ambiguity_risk": 0,
    }
    assert body["formula_refinement_results"]["card_id"] == "RECT_PROFESSION_CHANGE_002_DRAFT"


def test_rectification_pro_can_select_marriage_union_v2_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "marriage_start"
    payload["settings"]["formula_card_id"] = "RECT_MARRIAGE_UNION_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_MARRIAGE_UNION_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 100
    assert result["priority_counts"] == {
        "golden": 30,
        "supporting": 42,
        "context": 28,
        "ambiguity_risk": 0,
    }
    assert body["formula_refinement_results"]["card_id"] == "RECT_MARRIAGE_UNION_002_DRAFT"


def test_rectification_pro_can_select_divorce_separation_v2_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "divorce_separation"
    payload["events"][0]["title"] = "Divorce"
    payload["settings"]["formula_card_id"] = "RECT_DIVORCE_SEPARATION_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_DIVORCE_SEPARATION_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 106
    assert result["priority_counts"] == {
        "golden": 34,
        "supporting": 38,
        "context": 34,
        "ambiguity_risk": 0,
    }
    assert body["formula_refinement_results"]["card_id"] == "RECT_DIVORCE_SEPARATION_002_DRAFT"


def test_rectification_pro_can_select_father_death_v2_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "death_father"
    payload["events"][0]["title"] = "Father death"
    payload["settings"]["formula_card_id"] = "RECT_FATHER_DEATH_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_FATHER_DEATH_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 82
    assert result["priority_counts"] == {
        "golden": 32,
        "supporting": 26,
        "context": 24,
        "ambiguity_risk": 0,
    }
    assert body["formula_refinement_results"]["card_id"] == "RECT_FATHER_DEATH_002_DRAFT"


def test_rectification_pro_can_select_mother_death_v2_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "death_mother"
    payload["events"][0]["title"] = "Mother death"
    payload["settings"]["formula_card_id"] = "RECT_MOTHER_DEATH_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_MOTHER_DEATH_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 78
    assert result["priority_counts"] == {
        "golden": 32,
        "supporting": 26,
        "context": 20,
        "ambiguity_risk": 0,
    }
    assert body["formula_refinement_results"]["card_id"] == "RECT_MOTHER_DEATH_002_DRAFT"


def test_rectification_pro_can_select_sibling_death_v2_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "death_sibling"
    payload["events"][0]["title"] = "Sibling death"
    payload["settings"]["formula_card_id"] = "RECT_SIBLING_DEATH_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_SIBLING_DEATH_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 84
    assert result["priority_counts"] == {
        "golden": 34,
        "supporting": 26,
        "context": 24,
        "ambiguity_risk": 0,
    }
    assert body["formula_refinement_results"]["card_id"] == "RECT_SIBLING_DEATH_002_DRAFT"


def test_rectification_pro_can_select_grandparent_death_v2_draft_card_explicitly(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "death_grandparent"
    payload["events"][0]["title"] = "Grandparent death"
    payload["settings"]["formula_card_id"] = "RECT_GRANDPARENT_DEATH_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    result = body["formula_test_mode_results"][0]
    assert result["card_id"] == "RECT_GRANDPARENT_DEATH_002_DRAFT"
    assert result["status"] == "draft"
    assert result["formulas_count"] == 80
    assert result["priority_counts"] == {
        "golden": 32,
        "supporting": 24,
        "context": 24,
        "ambiguity_risk": 0,
    }
    assert body["formula_refinement_results"]["card_id"] == "RECT_GRANDPARENT_DEATH_002_DRAFT"


def test_rectification_pro_can_compare_v1_and_v2_cards(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["settings"]["formula_card_id"] = "RECT_CHILD_BIRTH_002_DRAFT"
    payload["settings"]["compare_formula_card_ids"] = [
        "RECT_CHILD_BIRTH_001",
        "RECT_CHILD_BIRTH_002_DRAFT",
    ]

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    comparison = body["formula_card_comparison"]
    assert comparison["enabled"] is True
    assert comparison["selected_card_id"] == "RECT_CHILD_BIRTH_002_DRAFT"
    assert comparison["baseline_card_id"] == "RECT_CHILD_BIRTH_001"
    items = comparison["items"]
    assert [item["card_id"] for item in items] == [
        "RECT_CHILD_BIRTH_001",
        "RECT_CHILD_BIRTH_002_DRAFT",
    ]
    assert items[0]["formulas_count"] == 6
    assert items[1]["formulas_count"] == 94
    assert "working_time_ranges_difference" in comparison["differences"]
    assert "best_candidate_difference" in comparison["differences"]
    assert "event_contribution_audit_difference" in comparison["differences"]
    assert "shared_rules" in comparison["differences"]
    assert "v1_only_rules" in comparison["differences"]
    assert "v2_added_rules" in comparison["differences"]
    assert "why_result_changed" in comparison["differences"]
    assert comparison["differences"]["v1_only_rules"] == []
    assert any(rule["id"] == "cusp_10_to_cusp_5" and rule["inherited_from_v1"] for rule in comparison["differences"]["shared_rules"])
    assert "formula_refinement_results" not in items[0]
    assert "formula_test_mode_results" not in items[0]
    assert "formula_refinement_results" not in items[1]
    assert "formula_test_mode_results" not in items[1]


def test_rectification_pro_can_compare_marriage_v1_and_v2_cards(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "marriage_start"
    payload["settings"]["formula_card_id"] = "RECT_MARRIAGE_UNION_002_DRAFT"
    payload["settings"]["compare_formula_card_ids"] = [
        "RECT_MARRIAGE_UNION_001",
        "RECT_MARRIAGE_UNION_002_DRAFT",
    ]

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    comparison = response.json()["formula_card_comparison"]
    assert comparison["enabled"] is True
    assert comparison["baseline_card_id"] == "RECT_MARRIAGE_UNION_001"
    assert comparison["selected_card_id"] == "RECT_MARRIAGE_UNION_002_DRAFT"
    assert [item["card_id"] for item in comparison["items"]] == [
        "RECT_MARRIAGE_UNION_001",
        "RECT_MARRIAGE_UNION_002_DRAFT",
    ]
    assert comparison["summary"]["items"][0]["formulas_count"] > 0
    assert comparison["summary"]["items"][1]["formulas_count"] == 100
    assert "larger rule pack" in comparison["differences"]["why_result_changed"]


def test_rectification_pro_can_run_explicit_multi_card_v2_report(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(3)
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["title"] = "Child birth"
    payload["events"][1]["event_type"] = "marriage_start"
    payload["events"][1]["title"] = "Marriage"
    payload["events"][2]["event_type"] = "profession_change"
    payload["events"][2]["title"] = "Profession"
    payload["settings"]["formula_card_ids"] = [
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
    ]

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    multi = body["formula_multi_card_report"]
    assert multi["enabled"] is True
    assert multi["multi_card_enabled"] is True
    assert multi["selected_card_ids"] == [
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
    ]
    assert multi["overall_best_candidate"]
    assert multi["overall_working_ranges"]
    assert {item["card_id"] for item in multi["card_contribution_audit"]} == {
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
    }
    assert {item["event_type"] for item in multi["event_type_contribution"]} == {
        "child_birth",
        "marriage_union",
        "profession_change",
    }
    assert body["formula_refinement_results"]["multi_card_enabled"] is True
    assert body["formula_refinement_results"]["selected_card_ids"] == multi["selected_card_ids"]
    assert "formula_test_mode_results" not in (body["formula_refinement_results"]["best_candidate"] or {})


def test_rectification_pro_can_run_explicit_multi_card_v2_report_with_extended_death_cards(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(8)
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["title"] = "Child birth"
    payload["events"][1]["event_type"] = "marriage_start"
    payload["events"][1]["title"] = "Marriage"
    payload["events"][2]["event_type"] = "profession_change"
    payload["events"][2]["title"] = "Profession"
    payload["events"][3]["event_type"] = "divorce_separation"
    payload["events"][3]["title"] = "Divorce"
    payload["events"][4]["event_type"] = "death_father"
    payload["events"][4]["title"] = "Father death"
    payload["events"][5]["event_type"] = "death_mother"
    payload["events"][5]["title"] = "Mother death"
    payload["events"][6]["event_type"] = "death_sibling"
    payload["events"][6]["title"] = "Sibling death"
    payload["events"][7]["event_type"] = "death_grandparent"
    payload["events"][7]["title"] = "Grandparent death"
    payload["settings"]["formula_card_ids"] = [
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
        "RECT_DIVORCE_SEPARATION_002_DRAFT",
        "RECT_FATHER_DEATH_002_DRAFT",
        "RECT_MOTHER_DEATH_002_DRAFT",
        "RECT_SIBLING_DEATH_002_DRAFT",
        "RECT_GRANDPARENT_DEATH_002_DRAFT",
    ]

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    multi = response.json()["formula_multi_card_report"]
    assert multi["enabled"] is True
    assert multi["multi_card_enabled"] is True
    assert multi["selected_card_ids"] == [
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
        "RECT_DIVORCE_SEPARATION_002_DRAFT",
        "RECT_FATHER_DEATH_002_DRAFT",
        "RECT_MOTHER_DEATH_002_DRAFT",
        "RECT_SIBLING_DEATH_002_DRAFT",
        "RECT_GRANDPARENT_DEATH_002_DRAFT",
    ]
    assert {item["card_id"] for item in multi["card_contribution_audit"]} == {
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
        "RECT_DIVORCE_SEPARATION_002_DRAFT",
        "RECT_FATHER_DEATH_002_DRAFT",
        "RECT_MOTHER_DEATH_002_DRAFT",
        "RECT_SIBLING_DEATH_002_DRAFT",
        "RECT_GRANDPARENT_DEATH_002_DRAFT",
    }
    assert {item["event_type"] for item in multi["event_type_contribution"]} == {
        "child_birth",
        "marriage_union",
        "profession_change",
        "divorce_separation",
        "death_father",
        "death_mother",
        "death_sibling",
        "death_grandparent",
    }


def test_rectification_pro_profession_v2_validation_report_table_matches_expert_columns(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "profession_change"
    payload["events"][0]["title"] = "Profession"
    payload["settings"]["formula_card_id"] = "RECT_PROFESSION_CHANGE_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    table = response.json()["formula_test_mode_results"][0]["validation_report_table"]
    assert "Formula | Rule | Priority | Formula role | Status" in table
    assert "Directed longitude" in table
    assert "Natal longitude" in table
    assert "Actual angle" in table
    assert "Exact angle" in table
    assert "Orb" in table
    assert "Orb limit" in table
    assert "Reject reason" in table


def test_rectification_pro_comparison_includes_compact_summary(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["settings"]["formula_card_id"] = "RECT_CHILD_BIRTH_002_DRAFT"
    payload["settings"]["compare_formula_card_ids"] = [
        "RECT_CHILD_BIRTH_001",
        "RECT_CHILD_BIRTH_002_DRAFT",
    ]

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    comparison = response.json()["formula_card_comparison"]
    summary = comparison["summary"]
    assert summary["baseline_card_id"] == "RECT_CHILD_BIRTH_001"
    assert summary["selected_card_id"] == "RECT_CHILD_BIRTH_002_DRAFT"
    assert "items" in summary and len(summary["items"]) == 2
    assert {"card_id", "formulas_count", "working_range", "best_candidate", "matched", "rejected", "missed", "event_contribution_score"}.issubset(summary["items"][0])
    assert "top_rejected_reasons" in summary["items"][1]
    assert "why_result_changed" in summary


def test_rectification_pro_comparison_summary_includes_context_score_and_unresolved_summary(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["settings"]["formula_card_id"] = "RECT_CHILD_BIRTH_002_DRAFT"
    payload["settings"]["compare_formula_card_ids"] = [
        "RECT_CHILD_BIRTH_001",
        "RECT_CHILD_BIRTH_002_DRAFT",
    ]

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    summary_items = response.json()["formula_card_comparison"]["summary"]["items"]
    assert "context_score" in summary_items[0]
    assert "unresolved_source_summary" in summary_items[1]


def test_rectification_pro_supporting_count_consistent_between_summary_and_event_audit(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["settings"]["formula_card_id"] = "RECT_CHILD_BIRTH_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    best = response.json()["formula_refinement_results"]["best_candidate"]
    total_supporting = sum(int(item.get("supporting_matched_count", 0)) for item in best["event_contribution_audit"])
    assert best["supporting_matched_count"] == total_supporting


def test_rectification_pro_context_score_is_visible_in_best_candidate_and_event_audit(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["settings"]["formula_card_id"] = "RECT_CHILD_BIRTH_002_DRAFT"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    best = response.json()["formula_refinement_results"]["best_candidate"]
    assert "context_score" in best
    assert "context_formula_score" in best["score_breakdown"]
    assert "context_matched_count" in best
    assert all("context_score" in item for item in best["event_contribution_audit"])


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
        "source_type",
        "target_type",
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
    assert "resolved_source_group" in report["rule_debug"][0]
    assert "resolved_target_group" in report["rule_debug"][0]
    assert "source_selector_decisions" in report["rule_debug"][0]
    assert "target_selector_decisions" in report["rule_debug"][0]


def test_rectification_pro_candidate_consistency_uses_best_candidate_time_and_manual_timezone(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["birth_date_local"] = "1978-03-19"
    payload["latitude"] = 40.2341666667
    payload["longitude"] = 69.6947222222
    payload["timezone_name"] = "Asia/Yekaterinburg"
    payload["timezone_mode"] = "manual"
    payload["timezone_offset"] = "+05:00"
    payload["asc_windows"] = [
        {
            "start_local": "1978-03-19T22:55:00",
            "end_local": "1978-03-19T23:05:00",
            "sign_name_en": "Scorpio",
            "sign_name_ru": "Скорпион",
        }
    ]
    payload["settings"]["formula_refinement_step_seconds"] = 30
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    best = body["formula_refinement_results"]["best_candidate"]
    consistency_fields = {
        "selected_candidate_time",
        "chart_build_time",
        "natal_houses_time",
        "rulers_resolved_time",
        "house_elements_resolved_time",
        "directed_points_time",
        "timezone_used",
    }
    assert consistency_fields.issubset(best)
    assert best["selected_candidate_time"] == best["candidate_time_local"]
    assert best["chart_build_time"] == best["candidate_time_local"]
    assert best["natal_houses_time"] == best["candidate_time_local"]
    assert best["rulers_resolved_time"] == best["candidate_time_local"]
    assert best["house_elements_resolved_time"] == best["candidate_time_local"]
    assert best["directed_points_time"] == best["candidate_time_local"]
    assert best["timezone_used"] == "GMT+05:00"
    assert best["timezone_source"] == "manual_offset"
    assert best["utc_offset"] == "+05:00"
    assert best["payload_path"] == "rectification_direct"
    assert best["coordinates_used"] == {"latitude": 40.2341666667, "longitude": 69.6947222222}

    formula_result = body["formula_test_mode_results"][0]
    candidate_consistency = formula_result["validation_report"]["candidate_consistency"]
    assert candidate_consistency["selected_candidate_time"] == best["candidate_time_local"]
    assert candidate_consistency["timezone_used"] == "GMT+05:00"
    assert candidate_consistency["timezone_source"] == "manual_offset"
    assert candidate_consistency["utc_offset"] == "+05:00"
    assert candidate_consistency["payload_path"] == "rectification_direct"
    assert candidate_consistency["coordinates_used"] == {"latitude": 40.2341666667, "longitude": 69.6947222222}
    assert "event_date_used" in formula_result["validation_report_table"]


def test_rectification_pro_ruler_resolution_debug_includes_type_and_weight(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    rule_debug = response.json()["formula_test_mode_results"][0]["validation_report"]["rule_debug"]
    resolution_items = [
        item
        for rule in rule_debug
        for item in [*(rule.get("source_ruler_resolution") or []), *(rule.get("target_ruler_resolution") or [])]
        if item.get("ruler_type")
    ]
    assert resolution_items
    assert all("weight" in item for item in resolution_items)
    assert all("ruler_system" in item for item in resolution_items)
    assert any(item.get("exclude_reason") == "ruler_type_not_allowed" for item in resolution_items)


def test_rectification_pro_labels_multiple_rulers_with_ruler_type(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    result = response.json()["formula_test_mode_results"][0]
    report = result["validation_report"]
    assert any(item.get("ruler_type") for item in report["directed_points_debug"])
    assert any(
        pair.get("source_ruler_type") or pair.get("target_ruler_type")
        for rule in report["rule_debug"]
        for pair in rule.get("checked_pairs", [])
    )


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
    assert "Source type" in table
    assert "Target type" in table
    assert "Resolved source group" in table
    assert "Resolved target group" in table
    assert "Directed Sun -> Natal Jupiter" in table


def test_rectification_pro_formula_refinement_finds_precise_child_birth_candidate(monkeypatch, tmp_path) -> None:
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
            "sign_name_ru": "РЎС‚СЂРµР»РµС†",
        }
    ]
    payload["settings"]["formula_refinement_step_seconds"] = 30
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    refinement = response.json()["formula_refinement_results"]
    best = refinement["best_candidate"]
    coarse = refinement["coarse_candidate"]
    assert refinement["scanned_candidates_count"] > 1
    assert best["candidate_time_local"] != "1978-03-19T22:55:00"
    reference_dt = datetime.fromisoformat("1978-03-19T22:59:45")
    coarse_dt = datetime.fromisoformat(coarse["candidate_time_local"])
    best_dt = datetime.fromisoformat(best["candidate_time_local"])
    assert abs((best_dt - reference_dt).total_seconds()) < abs((coarse_dt - reference_dt).total_seconds())
    assert abs((best_dt - reference_dt).total_seconds()) <= 180
    assert best["matched_count"] >= 3
    assert best["score"] > 0


def test_rectification_pro_formula_refinement_uses_reference_triplet(monkeypatch, tmp_path) -> None:
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
            "sign_name_ru": "РЎС‚СЂРµР»РµС†",
        }
    ]
    payload["settings"]["formula_refinement_step_seconds"] = 30
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    best = body["formula_refinement_results"]["best_candidate"]
    table = body["formula_test_mode_results"][0]["validation_report_table"]
    assert "Directed ruler_4 -> Natal house_element_5 | ruler_4_to_house_element_5 | golden | event_confirmation | matched" in table
    assert "Directed Sun -> Natal Jupiter | sun_to_jupiter | golden | event_confirmation | matched" in table
    assert "Directed cusp_6 -> Natal Sun | cusp_6_to_sun | golden | time_refinement | matched" in table


def test_rectification_pro_formula_refinement_returns_scoring_breakdown(monkeypatch, tmp_path) -> None:
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
    payload["settings"]["formula_refinement_step_seconds"] = 30
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    best = response.json()["formula_refinement_results"]["best_candidate"]
    assert {"score_breakdown", "matched_count", "rejected_count", "missing_count"}.issubset(best)
    assert {
        "golden_formula_score",
        "golden_orb_quality_score",
        "supporting_formula_score",
        "supporting_bonus",
        "rejected_penalty",
        "missing_penalty",
    }.issubset(
        best["score_breakdown"]
    )


def test_rectification_pro_formula_refinement_separates_golden_and_supporting(monkeypatch, tmp_path) -> None:
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
    payload["settings"]["formula_refinement_step_seconds"] = 30
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    best = response.json()["formula_refinement_results"]["best_candidate"]
    assert {"golden_matched_count", "golden_orb_sum", "supporting_matched_count", "supporting_bonus"}.issubset(best)
    assert best["golden_matched_count"] >= 3
    assert best["supporting_matched_count"] >= 0
    assert isinstance(best["selection_reason"], str) and best["selection_reason"]
    assert "event_confirmation_score" in best
    assert "time_refinement_score" in best


def test_rectification_pro_formula_refinement_supporting_match_does_not_overpower_golden_ranking(monkeypatch, tmp_path) -> None:
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
    payload["settings"]["formula_refinement_step_seconds"] = 30
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    top = response.json()["formula_refinement_results"]["top_candidates"]
    best = top[0]
    reference = next((item for item in top if item["candidate_time_local"] == "1978-03-19T22:59:45"), None)
    assert best["golden_matched_count"] == 3
    assert "golden" in best["selection_reason"].lower()
    if reference is not None:
        assert reference["golden_matched_count"] == 3
        assert best["golden_orb_sum"] <= reference["golden_orb_sum"]


def test_rectification_pro_formula_refinement_returns_working_time_range_and_reference(monkeypatch, tmp_path) -> None:
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
            "sign_name_en": "Scorpio",
            "sign_name_ru": "Скорпион",
        }
    ]
    payload["settings"]["formula_refinement_step_seconds"] = 30
    payload["settings"]["formula_reference_time_local"] = "1978-03-19T22:59:45"
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    refinement = response.json()["formula_refinement_results"]
    assert isinstance(refinement["working_time_ranges"], list)
    assert refinement["working_time_ranges"]
    working_range = refinement["working_time_range"]
    assert working_range["start_local"] <= "1978-03-19T22:57:00"
    assert working_range["end_local"] >= "1978-03-19T22:59:45"
    assert refinement["reference_time"]["provided"] == "1978-03-19T22:59:45"
    assert refinement["reference_time"]["inside_working_time_range"] is True
    assert refinement["best_candidate"]["candidate_time_local"] != refinement["reference_time"]["provided"]


def test_formula_refinement_service_can_build_multiple_working_time_ranges() -> None:
    candidates = [
        {
            "candidate_time_local": "1978-03-19T22:55:00",
            "golden_matched_count": 3,
            "golden_orb_sum": 1.2,
            "supporting_matched_count": 1,
            "supporting_bonus": 1.0,
            "score": 44.0,
            "selection_reason": "",
        },
        {
            "candidate_time_local": "1978-03-19T22:55:30",
            "golden_matched_count": 3,
            "golden_orb_sum": 1.1,
            "supporting_matched_count": 1,
            "supporting_bonus": 1.0,
            "score": 45.0,
            "selection_reason": "",
        },
        {
            "candidate_time_local": "1978-03-19T22:57:00",
            "golden_matched_count": 2,
            "golden_orb_sum": 2.1,
            "supporting_matched_count": 0,
            "supporting_bonus": 0.0,
            "score": 20.0,
            "selection_reason": "",
        },
        {
            "candidate_time_local": "1978-03-19T22:58:00",
            "golden_matched_count": 3,
            "golden_orb_sum": 1.3,
            "supporting_matched_count": 0,
            "supporting_bonus": 0.2,
            "score": 43.0,
            "selection_reason": "",
        },
        {
            "candidate_time_local": "1978-03-19T22:58:30",
            "golden_matched_count": 3,
            "golden_orb_sum": 1.0,
            "supporting_matched_count": 1,
            "supporting_bonus": 0.9,
            "score": 46.0,
            "selection_reason": "",
        },
    ]
    ranges = FormulaRefinementService._build_working_time_ranges(candidates, 30)
    primary = FormulaRefinementService._select_primary_working_time_range(
        working_time_ranges=ranges,
        best_candidate={"candidate_time_local": "1978-03-19T22:58:30"},
    )

    assert len(ranges) == 2
    assert ranges[0]["start_local"] == "1978-03-19T22:55:00"
    assert ranges[0]["end_local"] == "1978-03-19T22:55:30"
    assert ranges[1]["start_local"] == "1978-03-19T22:58:00"
    assert ranges[1]["end_local"] == "1978-03-19T22:58:30"
    assert ranges[1]["best_candidate"] == "1978-03-19T22:58:30"
    assert primary == ranges[1]


def test_rectification_pro_formula_refinement_returns_event_contribution_audit(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(6)
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["date_text"] = "2005-11-07"
    payload["events"][0]["start_date"] = "2005-11-07"
    payload["events"][0]["end_date"] = "2005-11-07"
    payload["events"][0]["title"] = "Child birth"

    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)

    assert response.status_code == 200
    best = response.json()["formula_refinement_results"]["best_candidate"]
    assert "event_contribution_audit" in best
    assert isinstance(best["event_contribution_audit"], list)
    assert best["event_contribution_audit"]
    audit_item = best["event_contribution_audit"][0]
    assert {
        "event_type",
        "event_date",
        "matched_count",
        "rejected_count",
        "missed_count",
        "score",
        "contribution_to_final_candidate",
    }.issubset(audit_item.keys())


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
