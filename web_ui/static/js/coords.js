// Авто-извлечено из main.js (build-split). Модуль: coords.
import { aspectOrbProfileEl, coordDmsWrapEl, coordValueFormatEl, datetimeLocalEl, datetimeLocalSecondsEl, datetimeUtcPreviewEl, latitudeDmsEl, latitudeEl, longitudeDmsEl, longitudeEl, rdSiderealModeEl, rdZodiacModeEl, rectSiderealModeEl, rectZodiacModeEl, siderealModeEl, timezoneModeEl, timezoneNameEl, timezoneOffsetEl, timezoneOffsetHintEl, timezoneStatusEl, wzApiBaseUrlEl, wzBirthDateEl, wzCityQueryEl, wzCoordDmsWrapEl, wzCoordValueFormatEl, wzHouseSystemEl, wzLatitudeDmsEl, wzLatitudeEl, wzLongitudeDmsEl, wzLongitudeEl, wzSiderealModeEl, wzTimezoneModeEl, wzTimezoneNameEl, wzTimezoneOffsetEl, wzTimezoneOffsetHintEl, wzZodiacModeEl, zodiacModeEl } from "./dom.js";
import { appState, sharedBirthContext } from "./state.js";
import { buildDateTimeWithSeconds, decimalToDms, normalizeCoordinateNumber, normalizeSecondValue, parseDateTimeLocalParts, parseDmsCoordinate, resolveTimezoneOffsetForDisplay } from "./validation.js";
import { getChartContextPatch, getWizardContextPatch, syncSharedBirthContext } from "./state-sync.js";
import { renderSharedCurrentData, setGenerateTechnicalDebug } from "./ui.js";

    export function withActiveCoordinateInput(inputId, callback) {
      appState.activeCoordinateInputId = inputId;
      try {
        callback();
      } finally {
        window.setTimeout(() => {
          if (appState.activeCoordinateInputId === inputId) {
            appState.activeCoordinateInputId = null;
          }
        }, 0);
      }
    }

    export function applySharedContextToForms() {
      const apiBase = sharedBirthContext.apiBaseUrl || "";
      document.getElementById("apiBaseUrl").value = apiBase;
      document.getElementById("rectApiBaseUrl").value = apiBase;
      document.getElementById("rdApiBaseUrl").value = apiBase;
      document.getElementById("reApiBaseUrl").value = apiBase;
      wzApiBaseUrlEl.value = apiBase;

      if (sharedBirthContext.cityQuery != null) {
        document.getElementById("cityQuery").value = sharedBirthContext.cityQuery;
        document.getElementById("rectCityQuery").value = sharedBirthContext.cityQuery;
        document.getElementById("rdCityQuery").value = sharedBirthContext.cityQuery;
        wzCityQueryEl.value = sharedBirthContext.cityQuery;
      }

      const lat = sharedBirthContext.latitude ?? "";
      const lon = sharedBirthContext.longitude ?? "";
      if (appState.activeCoordinateInputId !== "latitude") {
        latitudeEl.value = lat;
      }
      if (appState.activeCoordinateInputId !== "longitude") {
        longitudeEl.value = lon;
      }
      document.getElementById("rectLatitude").value = lat;
      document.getElementById("rectLongitude").value = lon;
      document.getElementById("rdLatitude").value = lat;
      document.getElementById("rdLongitude").value = lon;
      if (appState.activeCoordinateInputId !== "wzLatitude") {
        wzLatitudeEl.value = lat;
      }
      if (appState.activeCoordinateInputId !== "wzLongitude") {
        wzLongitudeEl.value = lon;
      }
      coordValueFormatEl.value = sharedBirthContext.coordValueFormat || "decimal";
      wzCoordValueFormatEl.value = sharedBirthContext.coordValueFormat || "decimal";
      updateCoordinateFormatUi();

      if (sharedBirthContext.birthDateLocal) {
        document.getElementById("rectBirthDate").value = sharedBirthContext.birthDateLocal;
        document.getElementById("rdBirthDate").value = sharedBirthContext.birthDateLocal;
        wzBirthDateEl.value = sharedBirthContext.birthDateLocal;
      }
      if (sharedBirthContext.birthDateTimeLocal) {
        setDateTimeWithSeconds(sharedBirthContext.birthDateTimeLocal, { syncShared: false });
      }

      timezoneModeEl.value = sharedBirthContext.timezoneMode || "auto";
      wzTimezoneModeEl.value = sharedBirthContext.timezoneMode || "auto";
      timezoneNameEl.value = sharedBirthContext.timezoneName || "";
      wzTimezoneNameEl.value = sharedBirthContext.timezoneName || "";
      timezoneOffsetEl.value = sharedBirthContext.timezoneMode === "manual"
        ? (sharedBirthContext.timezoneOffset || "+05:00")
        : (sharedBirthContext.timezoneResolvedOffset || "auto");
      wzTimezoneOffsetEl.value = sharedBirthContext.timezoneMode === "manual"
        ? (sharedBirthContext.timezoneOffset || "+05:00")
        : (sharedBirthContext.timezoneResolvedOffset || "auto");

      document.getElementById("houseSystem").value = sharedBirthContext.houseSystem || "P";
      document.getElementById("rectHouseSystem").value = sharedBirthContext.houseSystem || "P";
      document.getElementById("rdHouseSystem").value = sharedBirthContext.houseSystem || "P";
      wzHouseSystemEl.value = sharedBirthContext.houseSystem || "P";

      aspectOrbProfileEl.value = sharedBirthContext.aspectOrbProfile || "avestan";
      zodiacModeEl.value = sharedBirthContext.zodiacMode || "tropical";
      rectZodiacModeEl.value = sharedBirthContext.zodiacMode || "tropical";
      rdZodiacModeEl.value = sharedBirthContext.zodiacMode || "tropical";
      wzZodiacModeEl.value = sharedBirthContext.zodiacMode || "tropical";

      siderealModeEl.value = sharedBirthContext.siderealMode || "";
      rectSiderealModeEl.value = sharedBirthContext.siderealMode || "";
      rdSiderealModeEl.value = sharedBirthContext.siderealMode || "";
      wzSiderealModeEl.value = sharedBirthContext.siderealMode || "";

      updateTimezoneUiState();
      renderSharedCurrentData();
    }

    export function setDateTimeWithSeconds(value, options = {}) {
      const fallbackSecond = normalizeSecondValue(datetimeLocalSecondsEl.value || "00");
      const forceSecond = options.forceSecond != null
        ? normalizeSecondValue(options.forceSecond)
        : null;
      const normalized = buildDateTimeWithSeconds(value, fallbackSecond, forceSecond);
      const parts = parseDateTimeLocalParts(normalized);
      if (!parts) {
        datetimeLocalEl.value = value || "";
        datetimeLocalSecondsEl.value = forceSecond || fallbackSecond;
        return datetimeLocalEl.value;
      }
      const second = forceSecond || parts.second || "00";
      if (datetimeLocalEl.value !== normalized) {
        datetimeLocalEl.value = normalized;
      }
      if (datetimeLocalSecondsEl.value !== second) {
        datetimeLocalSecondsEl.value = second;
      }
      if (options.syncShared !== false) {
        sharedBirthContext.birthDateTimeLocal = normalized;
      }
      return normalized;
    }

    export function buildCoordinateContextPatch(source = "chart", options = {}) {
      const format = sharedBirthContext.coordValueFormat || "decimal";
      const preferredSource = options.preferredSource || format;
      const useWizard = source === "wizard";
      const rawLatDecimal = useWizard ? String(wzLatitudeEl.value || "") : String(latitudeEl.value || "");
      const rawLonDecimal = useWizard ? String(wzLongitudeEl.value || "") : String(longitudeEl.value || "");
      const rawLatDms = useWizard ? wzLatitudeDmsEl.value.trim() : latitudeDmsEl.value.trim();
      const rawLonDms = useWizard ? wzLongitudeDmsEl.value.trim() : longitudeDmsEl.value.trim();

      let latitude = normalizeCoordinateNumber(rawLatDecimal);
      let longitude = normalizeCoordinateNumber(rawLonDecimal);
      if (preferredSource === "dms") {
        latitude = parseDmsCoordinate(rawLatDms, "lat");
        longitude = parseDmsCoordinate(rawLonDms, "lon");
      }

      if (Number.isFinite(latitude)) {
        const normalizedLatitude = Number(latitude).toFixed(6);
        if (appState.activeCoordinateInputId !== "latitude") {
          latitudeEl.value = normalizedLatitude;
        }
        if (appState.activeCoordinateInputId !== "wzLatitude") {
          wzLatitudeEl.value = normalizedLatitude;
        }
      }
      if (Number.isFinite(longitude)) {
        const normalizedLongitude = Number(longitude).toFixed(6);
        if (appState.activeCoordinateInputId !== "longitude") {
          longitudeEl.value = normalizedLongitude;
        }
        if (appState.activeCoordinateInputId !== "wzLongitude") {
          wzLongitudeEl.value = normalizedLongitude;
        }
      }
      const normalizedLatDms = Number.isFinite(latitude) ? decimalToDms(Number(latitude), "lat") : null;
      const normalizedLonDms = Number.isFinite(longitude) ? decimalToDms(Number(longitude), "lon") : null;
      if (normalizedLatDms && appState.activeCoordinateInputId !== "latitudeDms" && appState.activeCoordinateInputId !== "wzLatitudeDms") {
        latitudeDmsEl.value = normalizedLatDms;
        wzLatitudeDmsEl.value = normalizedLatDms;
      }
      if (normalizedLonDms && appState.activeCoordinateInputId !== "longitudeDms" && appState.activeCoordinateInputId !== "wzLongitudeDms") {
        longitudeDmsEl.value = normalizedLonDms;
        wzLongitudeDmsEl.value = normalizedLonDms;
      }

      setGenerateTechnicalDebug({
        ...(appState.lastGenerateTechnicalDebug || {}),
        coordinates_debug: {
          format,
          preferred_source: preferredSource,
          source,
          latitude_input: preferredSource === "dms" ? rawLatDms : rawLatDecimal,
          longitude_input: preferredSource === "dms" ? rawLonDms : rawLonDecimal,
          latitude_decimal: Number.isFinite(latitude) ? Number(latitude) : null,
          longitude_decimal: Number.isFinite(longitude) ? Number(longitude) : null,
        },
      });

      return {
        coordValueFormat: format,
        latitude: Number.isFinite(latitude) ? Number(latitude) : null,
        longitude: Number.isFinite(longitude) ? Number(longitude) : null,
        latitudeDms: normalizedLatDms || null,
        longitudeDms: normalizedLonDms || null,
      };
    }

    export function updateCoordinateFormatUi() {
      const format = sharedBirthContext.coordValueFormat || "decimal";
      coordValueFormatEl.value = format;
      wzCoordValueFormatEl.value = format;
      const isDms = format === "dms";
      coordDmsWrapEl.classList.toggle("hidden", !isDms);
      wzCoordDmsWrapEl.classList.toggle("hidden", !isDms);

      if (Number.isFinite(sharedBirthContext.latitude) && Number.isFinite(sharedBirthContext.longitude)) {
        const latDms = decimalToDms(Number(sharedBirthContext.latitude), "lat");
        const lonDms = decimalToDms(Number(sharedBirthContext.longitude), "lon");
        if (appState.activeCoordinateInputId !== "latitudeDms") {
          latitudeDmsEl.value = latDms;
        }
        if (appState.activeCoordinateInputId !== "longitudeDms") {
          longitudeDmsEl.value = lonDms;
        }
        if (appState.activeCoordinateInputId !== "wzLatitudeDms") {
          wzLatitudeDmsEl.value = latDms;
        }
        if (appState.activeCoordinateInputId !== "wzLongitudeDms") {
          wzLongitudeDmsEl.value = lonDms;
        }
      } else {
        if (appState.activeCoordinateInputId !== "latitudeDms") {
          latitudeDmsEl.value = "";
        }
        if (appState.activeCoordinateInputId !== "longitudeDms") {
          longitudeDmsEl.value = "";
        }
        if (appState.activeCoordinateInputId !== "wzLatitudeDms") {
          wzLatitudeDmsEl.value = "";
        }
        if (appState.activeCoordinateInputId !== "wzLongitudeDms") {
          wzLongitudeDmsEl.value = "";
        }
      }
    }

    export function fillOffsets() {
      for (let h = -12; h <= 14; h++) {
        const sign = h >= 0 ? "+" : "-";
        const abs = Math.abs(h).toString().padStart(2, "0");
        const val = `${sign}${abs}:00`;
        const opt = document.createElement("option");
        opt.value = val;
        opt.textContent = val;
        timezoneOffsetEl.appendChild(opt);
      }
      timezoneOffsetEl.value = "+05:00";
    }

    export function fillSecondOptions() {
      datetimeLocalSecondsEl.innerHTML = "";
      for (let second = 0; second <= 59; second += 1) {
        const value = String(second).padStart(2, "0");
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        datetimeLocalSecondsEl.appendChild(option);
      }
      datetimeLocalSecondsEl.value = "00";
    }

    export function nowLocalInputValue() {
      const now = new Date();
      now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
      const base = now.toISOString().slice(0, 16);
      return `${base}:00`;
    }

    export function todayLocalDateValue() {
      const now = new Date();
      now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
      return now.toISOString().slice(0, 10);
    }

    export function calculateUtcPreview() {
      setDateTimeWithSeconds(datetimeLocalEl.value, {
        syncShared: false,
        forceSecond: datetimeLocalSecondsEl.value,
      });
      if (!datetimeLocalEl.value) {
        datetimeUtcPreviewEl.value = "";
        return;
      }
      if (timezoneModeEl.value === "auto") {
        datetimeUtcPreviewEl.value = "auto (расчёт на сервере по timezone_name)";
        return;
      }
      const dt = new Date(datetimeLocalEl.value);
      const offset = timezoneOffsetEl.value;
      const sign = offset.startsWith("+") ? 1 : -1;
      const hours = Number(offset.slice(1, 3));
      const mins = Number(offset.slice(4, 6));
      const deltaMs = sign * (hours * 60 + mins) * 60 * 1000;
      const utc = new Date(dt.getTime() - deltaMs);
      datetimeUtcPreviewEl.value = utc.toISOString().replace(".000", "");
    }

    export function ensureSelectDisplayValue(selectEl, value) {
      const normalized = value || "auto";
      let option = Array.from(selectEl.options).find((item) => item.value === normalized);
      if (!option) {
        option = document.createElement("option");
        option.value = normalized;
        option.textContent = normalized;
        option.dataset.ephemeral = "true";
        selectEl.appendChild(option);
      }
      Array.from(selectEl.options)
        .filter((item) => item.dataset.ephemeral === "true" && item.value !== normalized)
        .forEach((item) => item.remove());
      selectEl.value = normalized;
    }

    export function updateTimezoneUiState() {
      const isAuto = timezoneModeEl.value === "auto";
      timezoneOffsetEl.disabled = isAuto;
      wzTimezoneOffsetEl.disabled = isAuto;
      const resolvedOffset = resolveTimezoneOffsetForDisplay(
        timezoneNameEl.value || wzTimezoneNameEl.value || sharedBirthContext.timezoneName,
        datetimeLocalEl.value || sharedBirthContext.birthDateTimeLocal,
        wzBirthDateEl.value || sharedBirthContext.birthDateLocal,
      );
      sharedBirthContext.timezoneResolvedOffset = resolvedOffset;
      if (isAuto) {
        ensureSelectDisplayValue(timezoneOffsetEl, resolvedOffset || "auto");
        ensureSelectDisplayValue(wzTimezoneOffsetEl, resolvedOffset || "auto");
        timezoneOffsetHintEl.textContent = "Рассчитывается автоматически по timezone name.";
        wzTimezoneOffsetHintEl.textContent = "Рассчитывается автоматически по timezone name.";
        if (timezoneNameEl.value) {
          timezoneStatusEl.textContent = `Часовой пояс определён автоматически: ${timezoneNameEl.value}, ${resolvedOffset || "auto"}`;
        } else {
          timezoneStatusEl.textContent = "Часовой пояс будет определён автоматически по координатам.";
        }
      } else {
        ensureSelectDisplayValue(timezoneOffsetEl, sharedBirthContext.timezoneOffset || timezoneOffsetEl.value || "+05:00");
        ensureSelectDisplayValue(wzTimezoneOffsetEl, sharedBirthContext.timezoneOffset || wzTimezoneOffsetEl.value || "+05:00");
        timezoneOffsetHintEl.textContent = "Используется ручной offset.";
        wzTimezoneOffsetHintEl.textContent = "Используется ручной offset.";
        timezoneStatusEl.textContent = `Часовой пояс указан вручную: ${timezoneOffsetEl.value}`;
      }
      renderSharedCurrentData();
      calculateUtcPreview();
    }

    export function syncFromDecimalInputs(source) {
      if (source === "wizard") {
        syncSharedBirthContext(getWizardContextPatch({ coordinateSource: "decimal" }), { silent: false });
      } else {
        syncSharedBirthContext(getChartContextPatch({ coordinateSource: "decimal" }), { silent: false });
      }
    }

    export function syncFromDmsInputs(source) {
      if (source === "wizard") {
        syncSharedBirthContext(getWizardContextPatch({ coordinateSource: "dms" }), { silent: false });
      } else {
        syncSharedBirthContext(getChartContextPatch({ coordinateSource: "dms" }), { silent: false });
      }
    }
