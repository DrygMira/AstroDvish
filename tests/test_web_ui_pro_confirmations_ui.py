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
    assert "entries=" not in html
    assert "matched_events=" not in html


def test_pro_ui_confirmations_do_not_use_only_first_match_per_event() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "extractProMatchDetails(item.matches[0])" not in html


def test_pro_ui_renders_formula_test_mode_blocks() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "formula_test_mode_results" in html
    assert "validation_report_table" in html
    assert "matched_formula_aspects" in html
    assert "formula_refinement_results" in html


def test_pro_ui_renders_direction_debug_labels_and_coordinates() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Direction debug / Проверка дирекций" in html
    assert "Directed longitude" in html
    assert "Natal longitude" in html
    assert "Actual angle" in html
    assert "Exact angle" in html
    assert "Orb limit" in html
    assert "Reject reason" in html
    assert "rule_debug" in html


def test_pro_ui_validation_report_table_is_rendered_with_visible_detailed_fields() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "tableLine.style.whiteSpace = \"pre-wrap\"" in html
    assert "Directed longitude" in html
    assert "Natal longitude" in html
    assert "Actual angle" in html
    assert "Exact angle" in html
    assert "Orb limit" in html
    assert "Formula role" in html
    assert "Priority" in html
    assert "Source type" in html
    assert "Target type" in html
    assert "Resolved source group" in html
    assert "Resolved target group" in html
    assert "Include reason" in html
    assert "Exclude reason" in html
    assert "closest_major_aspect_mismatch" in html


def test_pro_ui_renders_formula_refinement_summary() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Refinement inside Asc window" in html
    assert "formula_refinement_results" in html
    assert "best_candidate" in html
    assert "coarse_candidate" in html
    assert "refinementBest.candidate_time_local" in html
    assert "matched_count" in html
    assert "rejected_count" in html
    assert "supported_step_seconds" in html
    assert "score_breakdown" in html
    assert "golden_matched_count" in html
    assert "golden_orb_sum" in html
    assert "supporting_bonus" in html
    assert "selection_reason" in html
    assert "working_time_ranges" in html
    assert "working_time_range" in html
    assert "reference_time" in html
    assert "Working range" in html
    assert "Working ranges" in html
    assert "Reference candidate" in html
    assert "Вклад событий в результат" in html
    assert "contribution_to_final_candidate" in html


def test_pro_ui_expected_labels_render_from_display_formula_not_stale_ids() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "rule.display_formula || rule.id" in html
    assert ".map((rule) => rule.id)" not in html
    assert "missingFormulaLinks.map((item) => item.display_formula || item.rule_id || \"—\")" in html


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
    assert "Ширина окна:" in html or "РЁРёСЂРёРЅР° РѕРєРЅР°:" in html
    assert "Это не точное время рождения." in html or "Р­С‚Рѕ РЅРµ С‚РѕС‡РЅРѕРµ РІСЂРµРјСЏ СЂРѕР¶РґРµРЅРёСЏ." in html


def test_pro_ui_contains_source_interval_and_clipping_explanation() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Источник Asc-интервала:" in html or "РСЃС‚РѕС‡РЅРёРє Asc-РёРЅС‚РµСЂРІР°Р»Р°:" in html
    assert "Окно было ограничено границами выбранной даты рождения." in html or "РћРєРЅРѕ Р±С‹Р»Рѕ РѕРіСЂР°РЅРёС‡РµРЅРѕ РіСЂР°РЅРёС†Р°РјРё РІС‹Р±СЂР°РЅРЅРѕР№ РґР°С‚С‹ СЂРѕР¶РґРµРЅРёСЏ." in html


def test_pro_ui_contains_expert_explainability_section() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'id="rpExplainDetails"' in html
    assert 'id="rpExplainBody"' in html
    assert "buildProExplainabilityHtml" in html


def test_pro_ui_explainability_mentions_stage1_events_methods_and_limitations() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Element scores" in html
    assert "Cross/Modality scores" in html
    assert "Метод пока является промежуточной проверкой, не финальным Direction Formula Engine." in html
    assert "getStage2RepeatCountHint" in html
    assert "summarizeMethodStats" in html


def test_pro_ui_hides_inactive_lunars_totems_in_main_confirmations() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'methodName === "lunars" || methodName === "totems"' in html
    assert "isMethodInactive(methodStats, methodName)" in html


def test_pro_ui_explainability_does_not_expose_api_keys() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "OPENAI_API_KEY" not in html
    assert "OPENROUTER_API_KEY" not in html


def test_pro_ui_contains_explicit_formula_card_selector_and_v1_v2_comparison_markers() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "formula_card_id" in html
    assert "compare_formula_card_ids" in html
    assert "RECT_CHILD_BIRTH_002_DRAFT" in html
    assert "V1 vs V2" in html
    assert "formula_card_comparison" in html
    assert "working_time_ranges_difference" in html
    assert "best_candidate_difference" in html
    assert "event_contribution_audit_difference" in html
    assert "shared_rules" in html
    assert "v1_only_rules" in html
    assert "v2_added_rules" in html
    assert "why_result_changed" in html


def test_pro_ui_contains_compact_v1_v2_summary_markers() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Comparison summary" in html
    assert "Working range" in html
    assert "Best candidate" in html
    assert "matched/rejected/missed" in html
    assert "top_rejected_reasons" in html


def test_pro_ui_shows_formula_card_counts_and_priority_tiers() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "formulas_count" in html
    assert "priority_counts" in html
    assert "golden" in html
    assert "supporting" in html
    assert "context" in html
    assert "ambiguity_risk" in html


def test_pro_ui_contains_preview_mode_loader_markers() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "proof_preview" in html
    assert "/api/preview/pro-result" in html
    assert "/api/preview/chart-result" in html
    assert "runUiProofPreviewFromQuery" in html


def test_pro_ui_contains_comparison_preview_mode_markers() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'previewMode === "comparison"' in html
    assert 'setTab("rect-events")' in html
    assert "rpFormulaComparisonEl.scrollIntoView" in html


def test_preview_pro_result_endpoint_returns_required_keys() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/api/preview/pro-result")
    assert response.status_code == 200
    payload = response.json()
    assert "formula_refinement_results" in payload
    assert "formula_test_mode_results" in payload
    assert "validation_report_table" in payload["formula_test_mode_results"][0]
    refinement = payload["formula_refinement_results"]
    assert "working_time_ranges" in refinement
    assert "best_candidate" in refinement
    assert "reference_time" in refinement
    assert "event_contribution_audit" in refinement["best_candidate"]
    report = payload["formula_test_mode_results"][0]["validation_report"]
    first_rule_debug = report["rule_debug"][0]
    assert "resolved_source_group" in first_rule_debug
    assert "resolved_target_group" in first_rule_debug
    assert "source_ruler_resolution" in first_rule_debug
    assert "source_selector_decisions" in first_rule_debug
    assert report["expected_by_card"]["direction_rules"][1]["aspect"] == "opposition"
    assert report["rejected_aspects"][0]["aspect_type"] == "opposition"
    assert report["missed_by_engine"][0]["reason"] == "over_orb_only"
    assert "ruler_type" in str(payload["formula_test_mode_results"][0]["validation_report"])


def test_preview_pro_result_endpoint_includes_enabled_v1_v2_comparison_summary() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/api/preview/pro-result")
    assert response.status_code == 200
    payload = response.json()
    comparison = payload["formula_card_comparison"]
    assert comparison["enabled"] is True
    assert comparison["baseline_card_id"] == "RECT_CHILD_BIRTH_001"
    assert comparison["selected_card_id"] == "RECT_CHILD_BIRTH_002_DRAFT"
    assert [item["card_id"] for item in comparison["items"]] == [
        "RECT_CHILD_BIRTH_001",
        "RECT_CHILD_BIRTH_002_DRAFT",
    ]
    summary = comparison["summary"]
    assert [item["card_id"] for item in summary["items"]] == [
        "RECT_CHILD_BIRTH_001",
        "RECT_CHILD_BIRTH_002_DRAFT",
    ]
    assert summary["items"][0]["formulas_count"] == 6
    assert summary["items"][1]["formulas_count"] == 94
    assert summary["items"][1]["top_rejected_reasons"][0]["reason"] == "over_orb"
    shared_rule_ids = {item["id"] for item in comparison["differences"]["shared_rules"]}
    assert {
        "cusp_10_to_cusp_5",
        "cusp_6_to_sun",
        "sun_to_jupiter",
        "cusp_5_to_chiron",
    }.issubset(shared_rule_ids)
    assert comparison["differences"]["v1_only_rules"] == []
    assert comparison["differences"]["why_result_changed"]


def test_preview_chart_result_endpoint_returns_chart_payload_for_modal() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/api/preview/chart-result")
    assert response.status_code == 200
    payload = response.json()
    assert payload["chart_status"] == "ok"
    assert "horoscope_text" in payload
    assert "chart_response" in payload
