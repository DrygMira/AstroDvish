from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_bundle import get_main_ui_bundle
import web_ui.main as web_ui_main


def test_main_ui_uses_premium_luxe_visual_markers_and_soft_transitions() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'href="static/css/styles.css"' in html
    assert 'class="card hero-card"' in html
    assert 'class="hero-title-wrap"' in html
    assert 'class="hero-kicker"' not in html
    assert "--accent-primary" in html
    assert "cubic-bezier(0.22, 1, 0.36, 1)" in html
    assert "scroll-behavior: smooth;" in html


def test_main_ui_uses_product_header_without_test_ports_copy() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "Ректификация времени рождения" in html
    assert "AstroDvish — ректификация времени рождения" not in html
    assert "Введите данные рождения, пройдите этапы уточнения и проверьте расчётные окна времени." in html
    assert "Тестовая веб-морда астросервиса" not in html
    assert "UI работает на порту 8014" not in html
    assert "API на 8013" not in html


def test_main_ui_hides_api_address_and_keeps_it_in_technical_mode() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'id="apiBaseUrl"' in html
    assert 'id="wzApiBaseUrl"' in html
    assert '<div class="hidden">' in html
    assert "Технический режим / отдельные модули" in html


def test_timezone_auto_ui_disables_manual_offset_and_shows_auto_resolution() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "timezoneOffsetEl.disabled = isAuto;" in html
    assert "wzTimezoneOffsetEl.disabled = isAuto;" in html
    assert "Рассчитывается автоматически по timezone name." in html
    assert "Используется ручной offset." in html
    assert "Europe/Moscow" in html


def test_timezone_auto_ui_uses_resolved_offset_text_not_stale_manual_value() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "sharedBirthContext.timezoneResolvedOffset" in html
    assert 'ensureSelectDisplayValue(timezoneOffsetEl, resolvedOffset || "auto");' in html
    assert 'ensureSelectDisplayValue(wzTimezoneOffsetEl, resolvedOffset || "auto");' in html


def test_timezone_auto_ui_uses_direct_rectification_birth_date_before_shared_fallback() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'export const rdBirthDateEl = document.getElementById("rdBirthDate");' in html
    assert 'export const rectBirthDateEl = document.getElementById("rectBirthDate");' in html
    assert "const timezoneDateValue =" in html
    assert "rdBirthDateEl?.value ||" in html
    assert "rectBirthDateEl?.value ||" in html
    assert "wzBirthDateEl.value ||" in html
    assert "sharedBirthContext.birthDateLocal;" in html
    assert "const sharedDateTimeValue = datetimeLocalEl.value || sharedBirthContext.birthDateTimeLocal;" in html
    assert 'sharedDateTimeValue.startsWith(`${timezoneDateValue}T`)' in html
    assert "? sharedDateTimeValue" in html


def test_main_ui_has_mobile_safe_birth_seconds_input_and_hint() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'id="datetimeLocalSeconds"' in html
    assert "Секунды важны для точного Asc/MC. Если неизвестны — оставьте 00." in html
    assert "mobile fallback" in html
    assert "fillSecondOptions()" in html
    assert "for (let second = 0; second <= 59; second += 1)" in html


def test_main_ui_does_not_truncate_birth_datetime_to_minutes() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "return `${base}:00`;" in html
    assert "setDateTimeWithSeconds(datetimeLocalEl.value, { syncShared: false });" in html
    assert "setDateTimeWithSeconds(nowLocalInputValue(), { syncShared: false });" in html
    assert "forceSecond: datetimeLocalSecondsEl.value" in html


def test_main_ui_supports_dms_coordinate_input_and_conversion_debug() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'id="coordValueFormat"' in html
    assert 'id="latitude" type="text"' in html
    assert 'id="longitude" type="text"' in html
    assert 'inputmode="decimal"' in html
    assert 'id="latitudeDms"' in html
    assert 'id="longitudeDms"' in html
    assert "parseDmsCoordinate(" in html
    assert "decimalToDms(" in html
    assert "coordinates_debug" in html
    assert "latitudeDms: normalizedLatDms || null" in html
    assert "longitudeDms: normalizedLonDms || null" in html
    assert "latitudeDms: Number.isFinite(latitude) ? decimalToDms(latitude, \"lat\") : null" in html


def test_main_ui_decimal_coordinate_inputs_preserve_manual_editing_while_syncing_other_fields() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "activeCoordinateInputId: null," in html
    assert "function withActiveCoordinateInput(inputId, callback)" in html
    assert "if (appState.activeCoordinateInputId !== \"latitude\") {" in html
    assert "if (appState.activeCoordinateInputId !== \"longitude\") {" in html


def test_main_ui_coordinate_sync_uses_source_of_edit_not_only_selected_format() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "function syncFromDecimalInputs(source)" in html
    assert "function syncFromDmsInputs(source)" in html
    assert "getChartContextPatch({ coordinateSource: \"decimal\" })" in html
    assert "getChartContextPatch({ coordinateSource: \"dms\" })" in html
    assert "getWizardContextPatch({ coordinateSource: \"decimal\" })" in html
    assert "getWizardContextPatch({ coordinateSource: \"dms\" })" in html


def test_main_ui_decimal_and_dms_paths_are_not_forced_by_coord_value_format() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "const preferredSource = options.preferredSource || format;" in html
    assert "if (preferredSource === \"dms\") {" in html
    assert "latitude_input: preferredSource === \"dms\" ? rawLatDms : rawLatDecimal," in html
    assert "longitude_input: preferredSource === \"dms\" ? rawLonDms : rawLonDecimal," in html


def test_main_ui_generate_payload_uses_datetime_with_seconds() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "const normalizedDateTime = setDateTimeWithSeconds(datetimeLocalEl.value, {" in html
    assert "forceSecond: datetimeLocalSecondsEl.value" in html
    assert "datetime_local: normalizedDateTime," in html


def test_main_ui_seconds_input_overrides_datetime_seconds() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "const forceSecond = options.forceSecond != null" in html
    assert "forceSecond: normalizedSecond" in html


def test_main_ui_sanitizes_openrouter_402_error_text() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "Карта рассчитана, но текстовая интерпретация сейчас недоступна. Попробуйте повторить позже." in html
    assert "OpenRouter" not in html
    assert "detail?.raw_error" in html


def test_main_ui_has_generate_technical_debug_fields() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "normalizeLlmReason" in html
    assert "provider: detail?.provider || null" in html
    assert "requested_max_tokens" in html
    assert "applied_max_tokens" in html
    assert "retried_with_lower_max_tokens" in html
    assert "#generateDebugBox," in html


def test_main_ui_deduplicates_llm_unavailable_message_in_status() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'data.warnings.filter((item) => item !== "llm_unavailable")' in html


def test_main_ui_has_humanized_openrouter_error_messages_for_common_statuses() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "Не удалось авторизоваться в сервисе модели. Обратитесь к администратору." in html
    assert "Сервис модели перегружен. Повторите попытку чуть позже." in html
    assert "Сервис модели временно недоступен. Попробуйте ещё раз позже." in html


def test_main_ui_supports_humanized_geocode_error_and_technical_debug() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "detail?.user_message" in html
    assert "#geocodeDebugBox {" in html


def test_main_ui_humanizes_non_json_proxy_errors() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "function humanizeNonJsonError(res, text)" in html
    assert 'normalized.includes("gateway time-out")' in html
    assert 'normalized.includes("temporary failure in name resolution")' in html
    assert "function fetchWithTimeout(url, options = {}, timeoutMs = 180000)" in html
    assert "V2 comparison may take up to 2 minutes." in html
    assert '}, 620000);' in html


def test_main_ui_humanizes_browser_level_fetch_failures() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'if (err instanceof TypeError)' in html
    assert "Соединение с сервером прервалось" in html


def test_main_ui_does_not_ship_ufa_city_or_coordinates_as_live_defaults() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'id="cityQuery" value="Уфа"' not in html
    assert 'id="wzCityQuery" value="Уфа"' not in html
    assert 'id="rectCityQuery" value="Уфа"' not in html
    assert 'id="rdCityQuery" value="Уфа"' not in html
    assert 'id="latitude" type="text" inputmode="decimal" value="54.7388"' not in html
    assert 'id="longitude" type="text" inputmode="decimal" value="55.9721"' not in html
    assert "sharedBirthContext.cityQuery = document.getElementById(\"cityQuery\").value.trim() || null;" in html


def test_main_ui_does_not_force_manual_plus_five_offset_as_initial_state() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'timezoneOffsetEl.value = "+05:00";' not in html
    assert 'wzTimezoneOffsetEl.value = "+05:00";' not in html
    assert 'sharedBirthContext.timezoneOffset = "+05:00"' not in html


def test_main_ui_does_not_hardcode_browser_localhost_api_base() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'value="http://127.0.0.1:8013"' not in html
    assert "По умолчанию используется внутренний API сервера." in html


def test_main_ui_has_horoscope_followup_actions_for_llm_cta() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert 'id="horoscopeFollowUpWrap"' in html
    assert 'id="horoscopeFollowUpHelpfulBtn"' in html
    assert 'id="horoscopeFollowUpSupportBtn"' in html
    assert 'id="horoscopeFollowUpAspectsBtn"' in html
    assert 'id="horoscopeFollowUpRecommendationsBtn"' in html
    assert 'id="horoscopeBackToMainBtn"' in html
    assert 'id="horoscopeContinuationWrap"' in html
    assert 'id="horoscopeContinuationMeta"' in html
    assert 'id="horoscopeContinuationBox"' in html
    assert 'class="btn secondary followup-btn"' in html
    assert 'generate({ followUpMode: "helpful" })' in html
    assert 'generate({ followUpMode: "support" })' in html
    assert 'generate({ followUpMode: "aspects" })' in html
    assert 'generate({ followUpMode: "recommendations" })' in html
    assert 'horoscopeBackToMainBtnEl.addEventListener("click"' in html
    assert 'setActiveFollowUpButton(followUpMode);' in html
    assert 'followup-btn-active' in html
    assert "ключевые рекомендации" in html.lower()
def test_main_ui_keeps_legacy_raw_api_hook_hidden_without_breaking_module_bootstrap() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "export function toggleRawApi()" in html
    assert 'toggleApiRawBtnEl?.classList.add("hidden");' in html
    assert 'apiRawWrapEl?.classList.add("hidden");' in html
