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
    assert "working_time_range" in html
    assert "reference_time" in html
    assert "Working range" in html


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
