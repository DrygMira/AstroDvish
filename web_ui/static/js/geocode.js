// Авто-извлечено из main.js (build-split). Модуль: geocode.
import { cityResultsEl, rdCityResultsEl, rectCityResultsEl, wzCityQueryEl, wzCityResultsEl } from "./dom.js";
import { sharedBirthContext } from "./state.js";
import { decimalToDms } from "./validation.js";
import { extractErrorText } from "./format.js";
import { syncSharedBirthContext } from "./state-sync.js";
import { setGeocodeTechnicalDebug, setRdStatus, setRectStatus, setStatus, setWzStatus } from "./ui.js";

    export async function geocodeSearch(query) {
      const res = await fetch("/api/geocode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      if (!res.ok) {
        setGeocodeTechnicalDebug(data?.detail || data || null);
        throw new Error(extractErrorText(data));
      }
      setGeocodeTechnicalDebug({
        provider: data?.provider || "unknown",
        fallback_provider_used: !!data?.fallback_provider_used,
        cached_result_used: !!data?.cached_result_used,
        debug: data?.debug || null,
      });
      return data.results || [];
    }

    export function fillCitySelect(selectEl, results) {
      selectEl.innerHTML = "";
      results.forEach((item, idx) => {
        const opt = document.createElement("option");
        opt.value = idx;
        const label = [item.name, item.admin1, item.country].filter(Boolean).join(", ");
        const tzName = item.timezone_name || item.timezone || "";
        opt.textContent = `${label} [${item.latitude}, ${item.longitude}] ${tzName}`;
        opt.dataset.label = label;
        opt.dataset.latitude = item.latitude;
        opt.dataset.longitude = item.longitude;
        opt.dataset.timezoneName = tzName;
        selectEl.appendChild(opt);
      });
      selectEl.dispatchEvent(new Event("change"));
    }

    export async function searchCity() {
      const query = document.getElementById("cityQuery").value.trim();
      if (!query) return;
      setStatus("Ищем город...");
      try {
        const results = await geocodeSearch(query);
        if (!results.length) {
          setStatus("Город не найден.");
          return;
        }
        fillCitySelect(cityResultsEl, results);
        setStatus("Город найден. Координаты обновлены.");
      } catch (err) {
        setStatus("Ошибка: " + err.message);
      }
    }

    export async function searchCityRect() {
      const query = document.getElementById("rectCityQuery").value.trim();
      if (!query) return;
      setRectStatus("Ищем город...");
      try {
        const results = await geocodeSearch(query);
        if (!results.length) {
          setRectStatus("Город не найден.");
          return;
        }
        fillCitySelect(rectCityResultsEl, results);
        setRectStatus("Город найден. Координаты обновлены.");
      } catch (err) {
        setRectStatus("Ошибка: " + err.message);
      }
    }

    export async function searchCityRectDialog() {
      const query = document.getElementById("rdCityQuery").value.trim();
      if (!query) return;
      setRdStatus("Ищем город...");
      try {
        const results = await geocodeSearch(query);
        if (!results.length) {
          setRdStatus("Город не найден.");
          return;
        }
        fillCitySelect(rdCityResultsEl, results);
        setRdStatus("Город найден. Координаты обновлены.");
      } catch (err) {
        setRdStatus("Ошибка: " + err.message);
      }
    }

    export async function searchCityWizard() {
      const query = wzCityQueryEl.value.trim();
      if (!query) return;
      setWzStatus("Ищем город...");
      try {
        const results = await geocodeSearch(query);
        if (!results.length) {
          setWzStatus("Город не найден.");
          return;
        }
        fillCitySelect(wzCityResultsEl, results);
        setWzStatus("Город найден. Координаты обновлены.");
      } catch (err) {
        setWzStatus("Ошибка: " + err.message);
      }
    }

    export function applyPlaceSelectionToSharedContext(option, cityQueryValue) {
      if (!option) return;
      const latitude = Number(option.dataset.latitude);
      const longitude = Number(option.dataset.longitude);
      syncSharedBirthContext({
        cityQuery: cityQueryValue || sharedBirthContext.cityQuery,
        selectedPlaceLabel: option.dataset.label || option.textContent || null,
        latitude,
        longitude,
        latitudeDms: Number.isFinite(latitude) ? decimalToDms(latitude, "lat") : null,
        longitudeDms: Number.isFinite(longitude) ? decimalToDms(longitude, "lon") : null,
        timezoneName: option.dataset.timezoneName || null,
        timezoneSource: option.dataset.timezoneName ? "geocode_result" : null,
      }, { silent: false });
    }
