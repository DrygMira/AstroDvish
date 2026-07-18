// Bootstrap: импорт модулей + навешивание обработчиков + init.
import { cityBlockEl, cityResultsEl, coordModeEl, coordValueFormatEl, datetimeLocalEl, datetimeLocalSecondsEl, expertDegreesExpandedToggleEl, horoscopeBackToMainBtnEl, horoscopeFollowUpAspectsBtnEl, horoscopeFollowUpHelpfulBtnEl, horoscopeFollowUpRecommendationsBtnEl, horoscopeFollowUpSupportBtnEl, latitudeDmsEl, latitudeEl, longitudeDmsEl, longitudeEl, modalEl, rdCityBlockEl, rdCityResultsEl, rdCoordModeEl, rdPromptWrapEl, rdShowPromptToggleEl, rdSiderealModeEl, rdZodiacModeEl, reTechJsonWrapEl, reToggleJsonBtnEl, rectCityBlockEl, rectCityResultsEl, rectCoordModeEl, rectJsonBoxEl, rectSiderealModeEl, rectZodiacModeEl, siderealModeEl, tabChartBtnEl, tabRectBtnEl, tabRectDialogBtnEl, tabRectEventsBtnEl, tabWizardBtnEl, techModeToggleBtnEl, timezoneModeEl, timezoneOffsetEl, toggleApiRawBtnEl, toggleExpertBtnEl, wzBirthDateEl, wzCityQueryEl, wzCityResultsEl, wzCoordValueFormatEl, wzLatitudeDmsEl, wzLatitudeEl, wzLongitudeDmsEl, wzLongitudeEl, wzSiderealModeEl, wzTimezoneOffsetEl, wzZodiacModeEl, zodiacModeEl } from "./dom.js";
import { appState, rectificationWizardState, sharedBirthContext } from "./state.js";
import { normalizeCoordinateNumber, normalizeSecondValue } from "./validation.js";
import { loadPrompt, loadRectificationPrompt } from "./api.js";
import { generate, hideHoroscopeContinuation, renderExpertTables, runRectification } from "./chart.js";
import { applySharedContextToForms, calculateUtcPreview, fillOffsets, fillSecondOptions, nowLocalInputValue, setDateTimeWithSeconds, syncFromDecimalInputs, syncFromDmsInputs, todayLocalDateValue, updateCoordinateFormatUi, updateTimezoneUiState, withActiveCoordinateInput } from "./coords.js";
import { applyPlaceSelectionToSharedContext, searchCity, searchCityRect, searchCityRectDialog, searchCityWizard } from "./geocode.js";
import { applyProTestEventsPreset, populateV2DraftCardOptions, runProRectification, runUiProofPreviewFromQuery } from "./pro.js";
import { resetRectDialogState, startRectificationDialog } from "./stage1.js";
import { continueRectEventsFlow, finalizeRectEventsFlow, resetRectEventsState, startRectEventsFlow } from "./stage2.js";
import { getChartContextPatch, getRectContextPatch, getRectDialogContextPatch, getWizardContextPatch, syncSharedBirthContext } from "./state-sync.js";
import { closeModal, setGenerateTechnicalDebug, setGeocodeTechnicalDebug, setRdStatus, setReStatus, setRpStatus, setStatus, setTab, setTechnicalMode, setWzStatus, setupMicroValidation, toggleExpertTable, toggleRawApi } from "./ui.js";
import { applyWizardBirthDataFromUi, renderWizardProgress, resetWizardDerivedState, resetWizardScenario, runWizardStep1, syncWizardToModuleFields, updateWizardContextFromCurrentStates } from "./wizard.js";


    tabWizardBtnEl.addEventListener("click", () => setTab("wizard"));
    tabChartBtnEl.addEventListener("click", () => setTab("chart"));
    tabRectBtnEl.addEventListener("click", () => {
      setTechnicalMode(true);
      setTab("rect");
    });
    tabRectDialogBtnEl.addEventListener("click", () => {
      setTechnicalMode(true);
      setTab("rect-dialog");
    });
    tabRectEventsBtnEl.addEventListener("click", () => {
      setTechnicalMode(true);
      setTab("rect-events");
    });
    techModeToggleBtnEl.addEventListener("click", () => setTechnicalMode(!appState.technicalModeOpen));
    const devModeToggleEl = document.getElementById("devModeToggle");
    if (devModeToggleEl) {
      devModeToggleEl.addEventListener("change", () => setTechnicalMode(devModeToggleEl.checked));
    }
    document.getElementById("wzEditDataBtn").addEventListener("click", () => {
      wzBirthDateEl.scrollIntoView({ behavior: "smooth", block: "center" });
      wzBirthDateEl.focus();
    });

    coordModeEl.addEventListener("change", () => {
      cityBlockEl.classList.toggle("hidden", coordModeEl.value !== "city");
    });
    rectCoordModeEl.addEventListener("change", () => {
      rectCityBlockEl.classList.toggle("hidden", rectCoordModeEl.value !== "city");
    });
    rdCoordModeEl.addEventListener("change", () => {
      rdCityBlockEl.classList.toggle("hidden", rdCoordModeEl.value !== "city");
    });

    document.getElementById("searchCityBtn").addEventListener("click", searchCity);
    document.getElementById("wzSearchCityBtn").addEventListener("click", searchCityWizard);
    document.getElementById("rectSearchCityBtn").addEventListener("click", searchCityRect);
    document.getElementById("rdSearchCityBtn").addEventListener("click", searchCityRectDialog);

    cityResultsEl.addEventListener("change", () => {
      const option = cityResultsEl.options[cityResultsEl.selectedIndex];
      if (!option) return;
      applyPlaceSelectionToSharedContext(option, document.getElementById("cityQuery").value.trim() || null);
    });
    wzCityResultsEl.addEventListener("change", () => {
      const option = wzCityResultsEl.options[wzCityResultsEl.selectedIndex];
      if (!option) return;
      applyPlaceSelectionToSharedContext(option, wzCityQueryEl.value.trim() || null);
      applyWizardBirthDataFromUi();
      setWzStatus("Координаты и timezone_name обновлены.");
    });
    rectCityResultsEl.addEventListener("change", () => {
      const option = rectCityResultsEl.options[rectCityResultsEl.selectedIndex];
      if (!option) return;
      applyPlaceSelectionToSharedContext(option, document.getElementById("rectCityQuery").value.trim() || null);
    });
    rdCityResultsEl.addEventListener("change", () => {
      const option = rdCityResultsEl.options[rdCityResultsEl.selectedIndex];
      if (!option) return;
      applyPlaceSelectionToSharedContext(option, document.getElementById("rdCityQuery").value.trim() || null);
    });

    document.getElementById("generateBtn").addEventListener("click", generate);
    horoscopeFollowUpHelpfulBtnEl.addEventListener("click", () => generate({ followUpMode: "helpful" }));
    horoscopeFollowUpSupportBtnEl.addEventListener("click", () => generate({ followUpMode: "support" }));
    horoscopeFollowUpAspectsBtnEl.addEventListener("click", () => generate({ followUpMode: "aspects" }));
    horoscopeFollowUpRecommendationsBtnEl.addEventListener("click", () => generate({ followUpMode: "recommendations" }));
    horoscopeBackToMainBtnEl.addEventListener("click", () => hideHoroscopeContinuation());
    document.getElementById("rectRunBtn").addEventListener("click", runRectification);
    document.getElementById("wzCalcAscBtn").addEventListener("click", runWizardStep1);
    document.getElementById("wzResetBtn").addEventListener("click", resetWizardScenario);
    document.getElementById("wzToStage1Btn").addEventListener("click", () => {
      if (!Array.isArray(rectificationWizardState.ascIntervals) || !rectificationWizardState.ascIntervals.length) {
        setWzStatus("Сначала завершите шаг 1 и рассчитайте Asc-интервалы.");
        return;
      }
      syncWizardToModuleFields();
      setTechnicalMode(true);
      setTab("rect-dialog");
      setWzStatus("Перешли к шагу 3. Запустите Stage 1.");
    });
    document.getElementById("wzOpenStage1Btn").addEventListener("click", () => {
      if (!Array.isArray(rectificationWizardState.ascIntervals) || !rectificationWizardState.ascIntervals.length) {
        setWzStatus("Сначала завершите шаг 2: нужны Asc-интервалы.");
        return;
      }
      syncWizardToModuleFields();
      setTechnicalMode(true);
      setTab("rect-dialog");
    });
    document.getElementById("wzOpenStage2Btn").addEventListener("click", () => {
      if (!rectificationWizardState.stage1.completed) {
        setWzStatus("Сначала завершите диалог по Asc.");
        return;
      }
      setTechnicalMode(true);
      setTab("rect-events");
    });
    document.getElementById("wzRunProBtn").addEventListener("click", runProRectification);
    document.getElementById("rdStartBtn").addEventListener("click", startRectificationDialog);
    document.getElementById("rdResetBtn").addEventListener("click", () => {
      resetRectDialogState();
      setRdStatus("Диалог сброшен.");
    });
    document.getElementById("rdReloadPromptBtn").addEventListener("click", async () => {
      try {
        await loadRectificationPrompt();
        setRdStatus("Prompt перезагружен из файла.");
      } catch (err) {
        setRdStatus("Ошибка загрузки prompt: " + err.message);
      }
    });
    rdShowPromptToggleEl.addEventListener("change", () => {
      rdPromptWrapEl.classList.toggle("hidden", !rdShowPromptToggleEl.checked);
    });

    document.getElementById("reStartBtn").addEventListener("click", startRectEventsFlow);
    document.getElementById("reResetBtn").addEventListener("click", () => {
      resetRectEventsState();
      updateWizardContextFromCurrentStates();
      setReStatus("Stage 2 и derived Pro/comparison state сброшены.");
    });
    document.getElementById("reAnswerBtn").addEventListener("click", () => continueRectEventsFlow(false));
    document.getElementById("reSkipBtn").addEventListener("click", () => continueRectEventsFlow(true));
    document.getElementById("reFinalizeBtn").addEventListener("click", finalizeRectEventsFlow);
    document.getElementById("reAddTestEventsBtn").addEventListener("click", applyProTestEventsPreset);
    document.getElementById("rpRunBtn").addEventListener("click", runProRectification);
    reToggleJsonBtnEl?.addEventListener("click", () => {
      const hiddenNow = reTechJsonWrapEl.classList.toggle("hidden");
      reToggleJsonBtnEl.textContent = hiddenNow
        ? "Показать технический JSON"
        : "Скрыть технический JSON";
    });

    document.getElementById("closeModalBtn").addEventListener("click", closeModal);
    document.getElementById("closeModalBtn2").addEventListener("click", closeModal);
    toggleExpertBtnEl.addEventListener("click", toggleExpertTable);
    expertDegreesExpandedToggleEl.addEventListener("change", () => {
      appState.expertDegreesExpanded = !!expertDegreesExpandedToggleEl.checked;
      if (appState.lastExpertRenderPayload) {
        renderExpertTables(
          appState.lastExpertRenderPayload.chartResponse,
          appState.lastExpertRenderPayload.timezonePayload,
          appState.lastExpertRenderPayload.warnings
        );
      }
    });
    toggleApiRawBtnEl?.addEventListener("click", toggleRawApi);
    timezoneOffsetEl.addEventListener("change", () => {
      syncSharedBirthContext(getChartContextPatch(), { silent: false });
      updateTimezoneUiState();
    });
    datetimeLocalEl.addEventListener("input", () => {
      setDateTimeWithSeconds(datetimeLocalEl.value, { syncShared: false });
      syncSharedBirthContext(getChartContextPatch(), { silent: false });
      calculateUtcPreview();
    });
    datetimeLocalSecondsEl.addEventListener("input", () => {
      const normalizedSecond = normalizeSecondValue(datetimeLocalSecondsEl.value || "00");
      datetimeLocalSecondsEl.value = normalizedSecond;
      setDateTimeWithSeconds(datetimeLocalEl.value, {
        syncShared: false,
        forceSecond: normalizedSecond,
      });
      syncSharedBirthContext(getChartContextPatch(), { silent: false });
      calculateUtcPreview();
    });

    coordValueFormatEl.addEventListener("change", () => {
      sharedBirthContext.coordValueFormat = coordValueFormatEl.value;
      updateCoordinateFormatUi();
      syncFromDecimalInputs("chart");
    });
    wzCoordValueFormatEl.addEventListener("change", () => {
      sharedBirthContext.coordValueFormat = wzCoordValueFormatEl.value;
      updateCoordinateFormatUi();
      syncFromDecimalInputs("wizard");
    });
    [latitudeDmsEl, longitudeDmsEl].forEach((el) => {
      el.addEventListener("input", () => {
        withActiveCoordinateInput(el.id, () => {
          syncFromDmsInputs("chart");
        });
      });
    });
    [wzLatitudeDmsEl, wzLongitudeDmsEl].forEach((el) => {
      el.addEventListener("input", () => {
        withActiveCoordinateInput(el.id, () => {
          syncFromDmsInputs("wizard");
        });
      });
    });
    [latitudeEl, longitudeEl].forEach((el) => {
      el.addEventListener("input", () => {
        withActiveCoordinateInput(el.id, () => {
          syncFromDecimalInputs("chart");
        });
      });
    });
    [wzLatitudeEl, wzLongitudeEl].forEach((el) => {
      el.addEventListener("input", () => {
        withActiveCoordinateInput(el.id, () => {
          syncFromDecimalInputs("wizard");
        });
      });
    });
    timezoneModeEl.addEventListener("change", () => {
      syncSharedBirthContext(getChartContextPatch(), { silent: false });
      updateTimezoneUiState();
    });

    zodiacModeEl.addEventListener("change", () => {
      const sidereal = zodiacModeEl.value === "sidereal";
      siderealModeEl.disabled = !sidereal;
      if (!sidereal) siderealModeEl.value = "";
    });
    rectZodiacModeEl.addEventListener("change", () => {
      const sidereal = rectZodiacModeEl.value === "sidereal";
      rectSiderealModeEl.disabled = !sidereal;
      if (!sidereal) rectSiderealModeEl.value = "";
    });
    rdZodiacModeEl.addEventListener("change", () => {
      const sidereal = rdZodiacModeEl.value === "sidereal";
      rdSiderealModeEl.disabled = !sidereal;
      if (!sidereal) rdSiderealModeEl.value = "";
    });
    wzZodiacModeEl.addEventListener("change", () => {
      const sidereal = wzZodiacModeEl.value === "sidereal";
      wzSiderealModeEl.disabled = !sidereal;
      if (!sidereal) wzSiderealModeEl.value = "";
    });

    window.addEventListener("click", (e) => { if (e.target === modalEl) closeModal(); });

    // ---- Микро-валидация полей координат (подсветка + подсказка формата) ----

    fillOffsets();
    fillSecondOptions();
    populateV2DraftCardOptions();
    for (let i = 0; i < timezoneOffsetEl.options.length; i++) {
      wzTimezoneOffsetEl.appendChild(timezoneOffsetEl.options[i].cloneNode(true));
    }
    wzTimezoneOffsetEl.value = "+00:00";
    setDateTimeWithSeconds(nowLocalInputValue(), { syncShared: false });
    timezoneModeEl.value = "auto";
    updateTimezoneUiState();
    appState.expertDegreesExpanded = !!expertDegreesExpandedToggleEl.checked;
    document.getElementById("rectBirthDate").value = todayLocalDateValue();
    document.getElementById("rdBirthDate").value = todayLocalDateValue();
    wzBirthDateEl.value = todayLocalDateValue();
    siderealModeEl.disabled = true;
    rectSiderealModeEl.disabled = true;
    rdSiderealModeEl.disabled = true;
    wzSiderealModeEl.disabled = true;
    if (rectJsonBoxEl) rectJsonBoxEl.textContent = "";
    resetRectDialogState();
    resetRectEventsState();
    resetWizardDerivedState();
    setTechnicalMode(false);
    setGenerateTechnicalDebug(null);
    setGeocodeTechnicalDebug(null);
    sharedBirthContext.birthDateLocal = todayLocalDateValue();
    sharedBirthContext.birthDateTimeLocal = datetimeLocalEl.value;
    sharedBirthContext.cityQuery = document.getElementById("cityQuery").value.trim() || null;
    sharedBirthContext.latitude = normalizeCoordinateNumber(latitudeEl.value);
    sharedBirthContext.longitude = normalizeCoordinateNumber(longitudeEl.value);
    sharedBirthContext.coordValueFormat = "decimal";
    applySharedContextToForms();
    updateWizardContextFromCurrentStates();
    renderWizardProgress();
    setupMicroValidation();

    [
      "apiBaseUrl", "rectApiBaseUrl", "rdApiBaseUrl", "reApiBaseUrl", "wzApiBaseUrl",
      "cityQuery", "rectCityQuery", "rdCityQuery", "wzCityQuery",
      "latitude", "longitude", "rectLatitude", "rectLongitude", "rdLatitude", "rdLongitude", "wzLatitude", "wzLongitude",
      "rectBirthDate", "rdBirthDate", "wzBirthDate",
      "houseSystem", "rectHouseSystem", "rdHouseSystem", "wzHouseSystem",
      "timezoneOffset", "wzTimezoneOffset", "timezoneMode", "wzTimezoneMode",
      "zodiacMode", "rectZodiacMode", "rdZodiacMode", "wzZodiacMode",
      "siderealMode", "rectSiderealMode", "rdSiderealMode", "wzSiderealMode",
      "aspectOrbProfile", "coordValueFormat", "wzCoordValueFormat",
    ].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("change", () => {
        if (["apiBaseUrl", "cityQuery", "latitude", "longitude", "houseSystem", "timezoneOffset", "timezoneMode", "zodiacMode", "siderealMode", "aspectOrbProfile"].includes(id)) {
          syncSharedBirthContext(getChartContextPatch(), { silent: false });
        } else if (id.startsWith("wz")) {
          syncSharedBirthContext(getWizardContextPatch(), { silent: false });
        } else if (id.startsWith("rect")) {
          syncSharedBirthContext(getRectContextPatch(), { silent: false });
        } else if (id.startsWith("rd")) {
          syncSharedBirthContext(getRectDialogContextPatch(), { silent: false });
        } else if (id === "reApiBaseUrl") {
          syncSharedBirthContext({ apiBaseUrl: document.getElementById("reApiBaseUrl").value.trim() || sharedBirthContext.apiBaseUrl }, { silent: true });
        }
      });
    });

    loadPrompt().catch(() => setStatus("Не удалось загрузить PROMPT.md"));
    loadRectificationPrompt().catch(() => setRdStatus("Не удалось загрузить PROMPT_RECTIFICATION_STAGE1.md"));
    runUiProofPreviewFromQuery().catch((err) => {
      setStatus("Ошибка proof preview: " + (err?.message || "unknown"));
      setRpStatus("Ошибка proof preview: " + (err?.message || "unknown"));
    });
