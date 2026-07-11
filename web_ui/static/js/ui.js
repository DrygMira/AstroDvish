// Авто-извлечено из main.js (build-split). Модуль: ui.
import { apiRawWrapEl, chartPanelEl, expertWrapEl, generateDebugBoxEl, geocodeDebugBoxEl, llmOverlayEl, llmOverlayElapsedEl, llmOverlayMessageEl, modalEl, rdStatusEl, reStatusEl, rectDialogPanelEl, rectEventsPanelEl, rectPanelEl, rectStatusEl, rpStatusEl, statusEl, tabChartBtnEl, tabRectBtnEl, tabRectDialogBtnEl, tabRectEventsBtnEl, tabWizardBtnEl, techModeContentEl, techModeHintEl, techModeToggleBtnEl, techPanelsWrapEl, toggleApiRawBtnEl, toggleExpertBtnEl, wizardPanelEl, wzCurrentDataSummaryEl, wzProStatusEl, wzStatusEl } from "./dom.js";
import { appState, sharedBirthContext } from "./state.js";
import { normalizeCoordinateNumber, parseDmsCoordinate } from "./validation.js";
import { formatElapsedDuration, normalizeLlmReason } from "./format.js";
import { generate } from "./chart.js";

    export function setTab(tabName) {
      tabWizardBtnEl.classList.toggle("active", tabName === "wizard");
      tabChartBtnEl.classList.toggle("active", tabName === "chart");
      tabRectBtnEl.classList.toggle("active", tabName === "rect");
      tabRectDialogBtnEl.classList.toggle("active", tabName === "rect-dialog");
      tabRectEventsBtnEl.classList.toggle("active", tabName === "rect-events");
      wizardPanelEl.classList.toggle("active", tabName === "wizard");
      chartPanelEl.classList.toggle("active", tabName === "chart");
      rectPanelEl.classList.toggle("active", tabName === "rect");
      rectDialogPanelEl.classList.toggle("active", tabName === "rect-dialog");
      rectEventsPanelEl.classList.toggle("active", tabName === "rect-events");
      techPanelsWrapEl.classList.toggle("hidden", !appState.technicalModeOpen);
    }

    export function setTechnicalMode(open) {
      appState.technicalModeOpen = !!open;
      techModeContentEl.classList.toggle("hidden", !appState.technicalModeOpen);
      techPanelsWrapEl.classList.toggle("hidden", !appState.technicalModeOpen);
      techModeToggleBtnEl.querySelector("span").textContent = appState.technicalModeOpen
        ? "▲ Технический режим / отдельные модули"
        : "▼ Технический режим / отдельные модули";
      techModeHintEl.textContent = appState.technicalModeOpen
        ? "Открыт: отдельные модули и debug"
        : "По умолчанию скрыт";
      if (!appState.technicalModeOpen) {
        rectPanelEl.classList.remove("active");
        rectDialogPanelEl.classList.remove("active");
        rectEventsPanelEl.classList.remove("active");
      }
      const devToggle = document.getElementById("devModeToggle");
      if (devToggle) devToggle.checked = appState.technicalModeOpen;
    }

    export function renderSharedCurrentData() {
      const houseLabel = sharedBirthContext.houseSystem === "P"
        ? "Плацидус"
        : (sharedBirthContext.houseSystem === "K" ? "Кох" : sharedBirthContext.houseSystem || "—");
      const zodiacLabel = sharedBirthContext.zodiacMode === "tropical" ? "тропический" : (sharedBirthContext.zodiacMode || "—");
      const orbLabel = sharedBirthContext.aspectOrbProfile === "avestan" ? "Авестийские" : (sharedBirthContext.aspectOrbProfile || "—");
      const timezoneLabel = sharedBirthContext.timezoneMode === "manual"
        ? `manual ${sharedBirthContext.timezoneOffset || "—"}`
        : `auto ${sharedBirthContext.timezoneName || ""} ${sharedBirthContext.timezoneResolvedOffset || "auto"}`.trim();
      const rows = [
        ["Дата", sharedBirthContext.birthDateLocal || "—"],
        ["Дата/время", sharedBirthContext.birthDateTimeLocal || "—"],
        ["Место", sharedBirthContext.selectedPlaceLabel || sharedBirthContext.cityQuery || "—"],
        ["Координаты", (sharedBirthContext.latitude != null && sharedBirthContext.longitude != null)
          ? `${sharedBirthContext.latitude}, ${sharedBirthContext.longitude}`
          : "—"],
        ["Timezone", timezoneLabel || "—"],
        ["Система домов", houseLabel],
        ["Зодиак", zodiacLabel],
        ["Орбисы", orbLabel],
      ];
      wzCurrentDataSummaryEl.innerHTML = rows.map(([label, value]) => `<div><strong>${label}:</strong> ${value}</div>`).join("");
    }

    export function setWzStatus(text) {
      wzStatusEl.textContent = text || "";
    }

    export function setWzProStatus(text) {
      wzProStatusEl.textContent = text || "";
    }

    export function setStatus(text) {
      statusEl.textContent = text || "";
    }

    export function setRectStatus(text) {
      rectStatusEl.textContent = text || "";
    }

    export function setRdStatus(text) {
      rdStatusEl.textContent = text || "";
    }

    export function setReStatus(text) {
      reStatusEl.textContent = text || "";
    }

    export function closeModal() {
      modalEl.classList.remove("active");
      expertWrapEl.classList.add("hidden");
      toggleExpertBtnEl.textContent = "Показать экспертную таблицу";
    }

    export function toggleExpertTable() {
      const hiddenNow = expertWrapEl.classList.toggle("hidden");
      toggleExpertBtnEl.textContent = hiddenNow
        ? "Показать экспертную таблицу"
        : "Скрыть экспертную таблицу";
    }

    export function toggleRawApi() {
      apiRawWrapEl?.classList.add("hidden");
      toggleApiRawBtnEl?.classList.add("hidden");
    }

    export function setGenerateTechnicalDebug(payload) {
      appState.lastGenerateTechnicalDebug = payload || null;
      if (!generateDebugBoxEl) return;
      generateDebugBoxEl.textContent = JSON.stringify(appState.lastGenerateTechnicalDebug || {
        info: "Нет ошибок /api/generate в текущей сессии.",
      }, null, 2);
    }

    export function setGeocodeTechnicalDebug(payload) {
      appState.lastGeocodeTechnicalDebug = payload || null;
      if (!geocodeDebugBoxEl) return;
      geocodeDebugBoxEl.textContent = JSON.stringify(appState.lastGeocodeTechnicalDebug || {
        info: "Нет данных /api/geocode в текущей сессии.",
      }, null, 2);
    }

    export function extractGenerateTechnicalDetail(payload) {
      const detail = payload?.detail || payload?.error || payload || {};
      const statusCode = detail?.status_code ?? payload?.status_code ?? null;
      return {
        provider: detail?.provider || null,
        scenario: detail?.scenario || detail?.request_kind || "generate",
        final_source: detail?.final_source || null,
        fallback_used: detail?.fallback_used ?? null,
        attempts: Array.isArray(detail?.attempts) ? detail.attempts : [],
        route: detail?.route || "/api/generate",
        status_code: statusCode,
        reason: normalizeLlmReason(detail?.reason),
        model: detail?.model ?? null,
        key_name: detail?.key_name ?? null,
        requested_max_tokens: detail?.requested_max_tokens ?? null,
        applied_max_tokens: detail?.applied_max_tokens ?? null,
        first_applied_max_tokens: detail?.first_applied_max_tokens ?? null,
        retried_with_lower_max_tokens: detail?.retried_with_lower_max_tokens ?? false,
        raw_error: typeof detail?.raw_error === "string" ? detail.raw_error : null,
      };
    }

    export function showLlmOverlay(message) {
      appState.llmOverlayStartedAt = Date.now();
      llmOverlayMessageEl.innerHTML = `<strong>${message || "Запрос в нейросеть отправлен, ждите..."}</strong>`;
      llmOverlayElapsedEl.textContent = "0 сек";
      llmOverlayEl.classList.add("active");

      if (appState.llmOverlayTimerId) {
        clearInterval(appState.llmOverlayTimerId);
      }
      appState.llmOverlayTimerId = setInterval(() => {
        const elapsedSeconds = Math.floor((Date.now() - appState.llmOverlayStartedAt) / 1000);
        llmOverlayElapsedEl.textContent = formatElapsedDuration(elapsedSeconds);
      }, 1000);
    }

    export function updateLlmOverlayMessage(message) {
      llmOverlayMessageEl.innerHTML = `<strong>${message || "Р—Р°РїСЂРѕСЃ РІ РЅРµР№СЂРѕСЃРµС‚СЊ РѕС‚РїСЂР°РІР»РµРЅ, Р¶РґРёС‚Рµ..."}</strong>`;
      llmOverlayEl.classList.add("active");
      if (!appState.llmOverlayTimerId) {
        appState.llmOverlayStartedAt = Date.now();
        llmOverlayElapsedEl.textContent = "0 СЃРµРє";
        appState.llmOverlayTimerId = setInterval(() => {
          const elapsedSeconds = Math.floor((Date.now() - appState.llmOverlayStartedAt) / 1000);
          llmOverlayElapsedEl.textContent = formatElapsedDuration(elapsedSeconds);
        }, 1000);
      }
    }

    export function hideLlmOverlay() {
      if (appState.llmOverlayTimerId) {
        clearInterval(appState.llmOverlayTimerId);
        appState.llmOverlayTimerId = null;
      }
      llmOverlayEl.classList.remove("active");
    }

    export function setRpStatus(text) {
      rpStatusEl.textContent = text || "";
    }

    export function setupMicroValidation() {
      const messages = {
        "lat-dec": "Широта: число −90…90 (например 54.7388)",
        "lon-dec": "Долгота: число −180…180 (например 55.9721)",
        "lat-dms": "Формат: 54°44'00\" N",
        "lon-dms": "Формат: 55°56'00\" E",
      };
      const fields = [
        { id: "latitude", kind: "lat-dec" }, { id: "longitude", kind: "lon-dec" },
        { id: "wzLatitude", kind: "lat-dec" }, { id: "wzLongitude", kind: "lon-dec" },
        { id: "rectLatitude", kind: "lat-dec" }, { id: "rectLongitude", kind: "lon-dec" },
        { id: "rdLatitude", kind: "lat-dec" }, { id: "rdLongitude", kind: "lon-dec" },
        { id: "latitudeDms", kind: "lat-dms" }, { id: "longitudeDms", kind: "lon-dms" },
        { id: "wzLatitudeDms", kind: "lat-dms" }, { id: "wzLongitudeDms", kind: "lon-dms" },
      ];
      function evaluate(kind, raw) {
        const v = (raw || "").trim();
        if (!v) return "empty";
        if (kind === "lat-dec" || kind === "lon-dec") {
          const n = normalizeCoordinateNumber(v);
          if (n === null) return "invalid";
          const limit = kind === "lat-dec" ? 90 : 180;
          return Math.abs(n) > limit ? "invalid" : "valid";
        }
        const axis = kind === "lat-dms" ? "lat" : "lon";
        return parseDmsCoordinate(v, axis) === null ? "invalid" : "valid";
      }
      fields.forEach((field) => {
        const el = document.getElementById(field.id);
        if (!el) return;
        let hint = el.parentElement && el.parentElement.querySelector('.field-hint[data-mv="1"]');
        if (!hint) {
          hint = document.createElement("div");
          hint.className = "field-hint";
          hint.setAttribute("data-mv", "1");
          el.insertAdjacentElement("afterend", hint);
        }
        const run = () => {
          const state = evaluate(field.kind, el.value);
          el.classList.remove("valid", "invalid");
          hint.classList.remove("ok", "error");
          if (state === "empty") { hint.textContent = ""; return; }
          if (state === "valid") {
            el.classList.add("valid");
            hint.classList.add("ok");
            hint.textContent = "✓ корректно";
          } else {
            el.classList.add("invalid");
            hint.classList.add("error");
            hint.textContent = messages[field.kind];
          }
        };
        el.addEventListener("input", run);
        el.addEventListener("blur", run);
      });
    }

    toggleRawApi();
