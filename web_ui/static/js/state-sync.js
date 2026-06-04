// Авто-извлечено из main.js (build-split). Модуль: state-sync.
import { aspectOrbProfileEl, datetimeLocalEl, datetimeLocalSecondsEl, rdSiderealModeEl, rdZodiacModeEl, rectIntervalsListEl, rectSiderealModeEl, rectZodiacModeEl, siderealModeEl, timezoneModeEl, timezoneNameEl, timezoneOffsetEl, wzApiBaseUrlEl, wzBirthDateEl, wzCityQueryEl, wzHouseSystemEl, wzSiderealModeEl, wzTimezoneModeEl, wzTimezoneNameEl, wzTimezoneOffsetEl, wzZodiacModeEl, zodiacModeEl } from "./dom.js";
import { rectificationWizardState, sharedBirthContext } from "./state.js";
import { applySharedContextToForms, buildCoordinateContextPatch, setDateTimeWithSeconds } from "./coords.js";
import { resetRectDialogState } from "./stage1.js";
import { resetRectEventsState } from "./stage2.js";
import { setRdStatus, setReStatus, setRectStatus, setWzStatus } from "./ui.js";
import { resetWizardDerivedState } from "./wizard.js";

    export function syncSharedBirthContext(patch, options = {}) {
      const previousCritical = JSON.stringify({
        birthDateLocal: sharedBirthContext.birthDateLocal,
        cityQuery: sharedBirthContext.cityQuery,
        latitude: sharedBirthContext.latitude,
        longitude: sharedBirthContext.longitude,
        timezoneMode: sharedBirthContext.timezoneMode,
        timezoneName: sharedBirthContext.timezoneName,
        timezoneOffset: sharedBirthContext.timezoneOffset,
        houseSystem: sharedBirthContext.houseSystem,
        zodiacMode: sharedBirthContext.zodiacMode,
      });
      Object.assign(sharedBirthContext, patch);
      applySharedContextToForms();

      const currentCritical = JSON.stringify({
        birthDateLocal: sharedBirthContext.birthDateLocal,
        cityQuery: sharedBirthContext.cityQuery,
        latitude: sharedBirthContext.latitude,
        longitude: sharedBirthContext.longitude,
        timezoneMode: sharedBirthContext.timezoneMode,
        timezoneName: sharedBirthContext.timezoneName,
        timezoneOffset: sharedBirthContext.timezoneOffset,
        houseSystem: sharedBirthContext.houseSystem,
        zodiacMode: sharedBirthContext.zodiacMode,
      });
      const hasDerivedResults =
        !!(Array.isArray(rectificationWizardState.ascIntervals) && rectificationWizardState.ascIntervals.length) ||
        rectificationWizardState.stage1.completed ||
        rectificationWizardState.stage2.completed ||
        rectificationWizardState.pro.completed;
      if (!options.silent && previousCritical !== currentCritical && hasDerivedResults) {
        const warningText = "Вы изменили данные рождения. Предыдущие интервалы, диалог и Pro-ректификация будут сброшены.";
        resetWizardDerivedState();
        resetRectDialogState();
        resetRectEventsState();
        rectIntervalsListEl.innerHTML = "";
        setWzStatus(warningText);
        setRectStatus(warningText);
        setRdStatus(warningText);
        setReStatus(warningText);
      }
    }

    export function getChartContextPatch(options = {}) {
      const normalizedDateTime = setDateTimeWithSeconds(datetimeLocalEl.value, {
        syncShared: false,
        forceSecond: datetimeLocalSecondsEl.value,
      });
      const coords = buildCoordinateContextPatch("chart", {
        preferredSource: options.coordinateSource || "decimal",
      });
      return {
        apiBaseUrl: document.getElementById("apiBaseUrl").value.trim() || "",
        birthDateLocal: normalizedDateTime ? normalizedDateTime.slice(0, 10) : sharedBirthContext.birthDateLocal,
        birthDateTimeLocal: normalizedDateTime || null,
        cityQuery: document.getElementById("cityQuery").value.trim() || null,
        latitude: coords.latitude,
        longitude: coords.longitude,
        coordValueFormat: coords.coordValueFormat,
        latitudeDms: coords.latitudeDms,
        longitudeDms: coords.longitudeDms,
        timezoneMode: timezoneModeEl.value,
        timezoneName: timezoneNameEl.value || null,
        timezoneOffset: timezoneOffsetEl.value || "+00:00",
        houseSystem: document.getElementById("houseSystem").value,
        zodiacMode: zodiacModeEl.value,
        siderealMode: zodiacModeEl.value === "sidereal" ? (siderealModeEl.value || null) : null,
        aspectOrbProfile: aspectOrbProfileEl.value,
      };
    }

    export function getWizardContextPatch(options = {}) {
      const coords = buildCoordinateContextPatch("wizard", {
        preferredSource: options.coordinateSource || "decimal",
      });
      return {
        apiBaseUrl: wzApiBaseUrlEl.value.trim() || "",
        birthDateLocal: wzBirthDateEl.value || null,
        cityQuery: wzCityQueryEl.value.trim() || null,
        latitude: coords.latitude,
        longitude: coords.longitude,
        coordValueFormat: coords.coordValueFormat,
        latitudeDms: coords.latitudeDms,
        longitudeDms: coords.longitudeDms,
        timezoneMode: wzTimezoneModeEl.value,
        timezoneName: wzTimezoneNameEl.value || null,
        timezoneOffset: wzTimezoneOffsetEl.value || "+00:00",
        houseSystem: wzHouseSystemEl.value,
        zodiacMode: wzZodiacModeEl.value,
        siderealMode: wzZodiacModeEl.value === "sidereal" ? (wzSiderealModeEl.value || null) : null,
      };
    }

    export function getRectContextPatch() {
      return {
        apiBaseUrl: document.getElementById("rectApiBaseUrl").value.trim() || "",
        birthDateLocal: document.getElementById("rectBirthDate").value || null,
        cityQuery: document.getElementById("rectCityQuery").value.trim() || null,
        latitude: Number(document.getElementById("rectLatitude").value),
        longitude: Number(document.getElementById("rectLongitude").value),
        timezoneMode: sharedBirthContext.timezoneMode || timezoneModeEl.value || "auto",
        timezoneName: sharedBirthContext.timezoneName || timezoneNameEl.value || null,
        timezoneOffset: sharedBirthContext.timezoneOffset || timezoneOffsetEl.value || "+00:00",
        houseSystem: document.getElementById("rectHouseSystem").value,
        zodiacMode: rectZodiacModeEl.value,
        siderealMode: rectZodiacModeEl.value === "sidereal" ? (rectSiderealModeEl.value || null) : null,
      };
    }

    export function getRectDialogContextPatch() {
      return {
        apiBaseUrl: document.getElementById("rdApiBaseUrl").value.trim() || "",
        birthDateLocal: document.getElementById("rdBirthDate").value || null,
        cityQuery: document.getElementById("rdCityQuery").value.trim() || null,
        latitude: Number(document.getElementById("rdLatitude").value),
        longitude: Number(document.getElementById("rdLongitude").value),
        timezoneMode: sharedBirthContext.timezoneMode || timezoneModeEl.value || "auto",
        timezoneName: sharedBirthContext.timezoneName || timezoneNameEl.value || null,
        timezoneOffset: sharedBirthContext.timezoneOffset || timezoneOffsetEl.value || "+00:00",
        houseSystem: document.getElementById("rdHouseSystem").value,
        zodiacMode: rdZodiacModeEl.value,
        siderealMode: rdZodiacModeEl.value === "sidereal" ? (rdSiderealModeEl.value || null) : null,
      };
    }
