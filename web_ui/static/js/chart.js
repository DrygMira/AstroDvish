// Авто-извлечено из main.js (build-split). Модуль: chart.
import { apiRawBoxEl, apiRawWrapEl, aspectOrbProfileEl, datetimeLocalEl, datetimeLocalSecondsEl, expertAnglesEl, expertAspectsEl, expertCuspsEl, expertObjectsEl, expertTimezoneEl, expertWrapEl, horoscopeBoxEl, modalEl, rectIntervalsListEl, rectJsonBoxEl, rectSiderealModeEl, rectZodiacModeEl, siderealModeEl, timezoneModeEl, timezoneNameEl, timezoneOffsetEl, toggleApiRawBtnEl, toggleExpertBtnEl, zodiacModeEl } from "./dom.js";
import { appState, sharedBirthContext } from "./state.js";
import { degreeToDms, extractErrorText, formatWarnings, renderTable, resolveAspectStrengthLabel, resolveMotionPhase } from "./format.js";
import { setDateTimeWithSeconds } from "./coords.js";
import { getChartContextPatch, getRectContextPatch, syncSharedBirthContext } from "./state-sync.js";
import { extractGenerateTechnicalDetail, renderSharedCurrentData, setGenerateTechnicalDebug, setRectStatus, setStatus } from "./ui.js";

    export function formatDegreeForExpert(value) {
      if (typeof value !== "number" || Number.isNaN(value)) return "—";
      return degreeToDms(value, appState.expertDegreesExpanded);
    }

    export function formatAbsoluteDegreeWithSign(value) {
      if (typeof value !== "number" || Number.isNaN(value)) return "—";
      const angle = angleToSignDegree(value);
      if (!angle) return "—";
      return `${angle.signName} ${angle.signDegree}`;
    }

    export function formatFormulaAngle(value) {
      if (typeof value !== "number" || Number.isNaN(value)) return "—";
      return degreeToDms(value, appState.expertDegreesExpanded);
    }

    export function buildFormulaRuleStatusRows(result) {
      const report = result?.validation_report || {};
      const ruleDebug = Array.isArray(report.rule_debug) ? report.rule_debug : [];
      const missingByRule = new Map(
        (Array.isArray(result?.missing_formula_links) ? result.missing_formula_links : [])
          .map((item) => [item.rule_id, item])
      );

      return ruleDebug.map((rule) => {
        const matchedPairs = Array.isArray(rule.matched_pairs) ? rule.matched_pairs : [];
        const rejectedPairs = Array.isArray(rule.rejected_pairs) ? rule.rejected_pairs : [];
        const checkedPairs = Array.isArray(rule.checked_pairs) ? rule.checked_pairs : [];
        const sample = matchedPairs[0] || rejectedPairs[0] || checkedPairs[0] || null;
        const missing = missingByRule.get(rule.rule_id) || null;

        let status = "missed";
        if (matchedPairs.length) {
          status = "matched";
        } else if (rejectedPairs.length) {
          status = "rejected";
        }

        let rejectReason = "—";
        if (status === "rejected") {
          rejectReason = rejectedPairs[0]?.reason || missing?.reason || "over_orb";
        } else if (status === "missed") {
          rejectReason = missing?.reason
            || (!Array.isArray(rule.resolved_sources) || !rule.resolved_sources.length
              ? "unresolved_source"
              : (!Array.isArray(rule.resolved_targets) || !rule.resolved_targets.length
                ? "unresolved_target"
                : "no_matching_aspect"));
        }

        return [
          rule.display_formula || rule.title || rule.rule_id || "—",
          rule.priority || rule.priority_tier || "—",
          rule.role || "—",
          status,
          sample?.directed_point || (Array.isArray(rule.resolved_sources) && rule.resolved_sources.length ? rule.resolved_sources.join(", ") : "—"),
          formatAbsoluteDegreeWithSign(sample?.directed_coordinate),
          sample?.natal_target || (Array.isArray(rule.resolved_targets) && rule.resolved_targets.length ? rule.resolved_targets.join(", ") : "—"),
          formatAbsoluteDegreeWithSign(sample?.natal_coordinate),
          sample?.aspect_type || "—",
          formatFormulaAngle(sample?.actual_angle),
          formatFormulaAngle(sample?.exact_angle),
          formatFormulaAngle(sample?.orb),
          formatFormulaAngle(sample?.orb_limit),
          rejectReason,
        ];
      });
    }

    export function buildFormulaAspectRows(items) {
      return (Array.isArray(items) ? items : []).map((match) => [
        match.formula_rule_matched || "—",
        match.match_status || "—",
        match.directed_point || "—",
        formatAbsoluteDegreeWithSign(match.directed_source_longitude),
        match.natal_target || "—",
        formatAbsoluteDegreeWithSign(match.natal_target_longitude),
        match.aspect_type || "—",
        formatFormulaAngle(match.actual_angle),
        formatFormulaAngle(match.exact_angle),
        formatFormulaAngle(match.orb),
        formatFormulaAngle(match.orb_limit),
        match.rejection_reason || "—",
      ]);
    }

    export function buildFormulaPointDebugRows(points, includeDirected) {
      return (Array.isArray(points) ? points : []).map((point) => {
        const row = [
          point.point_name || "—",
          formatAbsoluteDegreeWithSign(point.natal_longitude),
        ];
        if (includeDirected) {
          row.push(formatAbsoluteDegreeWithSign(point.directed_longitude));
          row.push(formatFormulaAngle(point.direction_arc));
        }
        return row;
      });
    }

    export function toSignDegreeText(item) {
      if (!item || typeof item !== "object") return "—";
      const sign = item.sign_name_en || "—";
      const degree = typeof item.sign_degree === "number" ? formatDegreeForExpert(item.sign_degree) : "—";
      return `${sign} ${degree}`;
    }

    export function angleToSignDegree(angleAbs) {
      if (typeof angleAbs !== "number" || Number.isNaN(angleAbs)) {
        return { signName: "—", signDegree: "—" };
      }
      const signs = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"];
      let normalized = angleAbs % 360;
      if (normalized < 0) normalized += 360;
      const signIndex = Math.floor(normalized / 30);
      const signDegree = normalized - signIndex * 30;
      return { signName: signs[signIndex], signDegree: formatDegreeForExpert(signDegree) };
    }

    export function renderExpertTables(chartResponse, timezonePayload, warnings) {
      appState.lastExpertRenderPayload = { chartResponse, timezonePayload, warnings };

      const objects = chartResponse?.objects || {};
      const houses = chartResponse?.houses || {};
      const aspects = Array.isArray(chartResponse?.aspects) ? chartResponse.aspects : [];
      const angles = chartResponse?.angles || {};
      const cuspDetails = houses.cusp_details || {};

      const objectOrder = [
        "sun","moon","mercury","venus","mars","jupiter","saturn","uranus","neptune","pluto","true_north_node","true_south_node","chiron"
      ];
      const objectLabels = {
        sun: "Солнце",
        moon: "Луна",
        mercury: "Меркурий",
        venus: "Венера",
        mars: "Марс",
        jupiter: "Юпитер",
        saturn: "Сатурн",
        uranus: "Уран",
        neptune: "Нептун",
        pluto: "Плутон",
        true_north_node: "Истинный Северный узел",
        true_south_node: "Истинный Южный узел",
        chiron: "Хирон",
      };
      const objectRows = objectOrder
        .filter((key) => objects[key])
        .map((key) => {
          const obj = objects[key];
          return [
            objectLabels[key] || key,
            obj.sign_name_en || "—",
            typeof obj.sign_degree === "number" ? formatDegreeForExpert(obj.sign_degree) : "—",
            typeof obj.absolute_degree_0_360 === "number" ? formatDegreeForExpert(obj.absolute_degree_0_360) : "—",
            obj.house ?? "—",
            resolveMotionPhase(obj),
          ];
        });
      expertObjectsEl.innerHTML = renderTable(
        ["Объект / планета", "Знак", "Градус в знаке", "Абсолютный градус 0–360", "Дом", "Фазы движения"],
        objectRows
      ) + "<div class='hint' style='margin-top:6px;'>D = директное, R = ретроградное, S = стационарное. Технически S определяется по порогу скорости (placeholder) и требует экспертной проверки.</div>";

      const angleMap = [["asc", "Asc"], ["mc", "MC"], ["desc", "Desc"], ["ic", "IC"]];
      const angleRows = angleMap
        .filter(([key]) => typeof angles[key] === "number")
        .map(([key, label]) => {
          const abs = angles[key];
          const signData = angleToSignDegree(abs);
          return [label, signData.signName, signData.signDegree, formatDegreeForExpert(abs)];
        });
      expertAnglesEl.innerHTML = renderTable(
        ["Угол", "Знак", "Градус", "Абсолютный градус"],
        angleRows
      );

      const cuspRows = Array.from({ length: 12 }, (_, i) => String(i + 1))
        .map((houseNo) => {
          const cusp = cuspDetails[houseNo];
          if (!cusp) {
            return [houseNo, "—", "—", "—"];
          }
          return [
            houseNo,
            cusp.sign_name_en || "—",
            typeof cusp.sign_degree === "number" ? formatDegreeForExpert(cusp.sign_degree) : "—",
            typeof cusp.absolute_degree_0_360 === "number" ? formatDegreeForExpert(cusp.absolute_degree_0_360) : "—",
          ];
        });
      expertCuspsEl.innerHTML = renderTable(
        ["Дом", "Знак куспида", "Градус в знаке", "Абсолютный градус"],
        cuspRows
      );

      const aspectRows = aspects.map((aspect) => [
        aspect.object_a || "—",
        aspect.aspect_type || "—",
        aspect.object_b || "—",
        formatDegreeForExpert(aspect.exact_angle),
        formatDegreeForExpert(aspect.actual_angle),
        formatDegreeForExpert(aspect.orb),
        resolveAspectStrengthLabel(aspect),
        aspect.applying === true ? "applying" : (aspect.applying === false ? "separating" : "—"),
      ]);
      expertAspectsEl.innerHTML = renderTable(
        ["Объект A", "Аспект", "Объект B", "Точный угол", "Фактический угол", "Отклонение (орбис)", "Сила", "Applying/Separating"],
        aspectRows
      );

      const warningText = Array.isArray(warnings) && warnings.length ? warnings.join(", ") : "—";
      const timezoneRows = [[
        timezonePayload?.mode || "—",
        timezonePayload?.timezone_name || "—",
        timezonePayload?.timezone_offset || "—",
        timezonePayload?.timezone_source || "—",
        timezonePayload?.datetime_local || "—",
        timezonePayload?.datetime_utc || "—",
        warningText,
      ]];
      expertTimezoneEl.innerHTML = renderTable(
        ["timezone mode", "timezone name", "timezone offset", "timezone source", "datetime local", "datetime UTC", "warnings"],
        timezoneRows
      );
    }

    export async function generate() {
      const chartContext = getChartContextPatch();
      syncSharedBirthContext(chartContext, { silent: false });
      setStatus("Выполняем расчёт...");
      const normalizedDateTime = setDateTimeWithSeconds(datetimeLocalEl.value, {
        syncShared: false,
        forceSecond: datetimeLocalSecondsEl.value,
      });
      const zodiacMode = zodiacModeEl.value;
      const sidMode = siderealModeEl.value || null;
      const body = {
        api_base_url: document.getElementById("apiBaseUrl").value.trim(),
        datetime_local: normalizedDateTime,
        timezone_mode: timezoneModeEl.value,
        timezone_offset: timezoneOffsetEl.value,
        timezone_name: timezoneNameEl.value || null,
        latitude: chartContext.latitude,
        longitude: chartContext.longitude,
        house_system: document.getElementById("houseSystem").value,
        aspect_orb_profile: aspectOrbProfileEl.value,
        zodiac_mode: zodiacMode,
        sidereal_mode: zodiacMode === "sidereal" ? sidMode : null,
        prompt_text: document.getElementById("promptText").value || "Сделай гороскоп по этим данным.",
      };
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setGenerateTechnicalDebug(extractGenerateTechnicalDetail(data));
        setStatus("Ошибка: " + extractErrorText(data));
        return;
      }
      if (data.llm_debug) {
        setGenerateTechnicalDebug(extractGenerateTechnicalDetail({ detail: data.llm_debug }));
      } else {
        setGenerateTechnicalDebug(null);
      }
      sharedBirthContext.timezoneSource = data.timezone?.timezone_source || sharedBirthContext.timezoneSource;
      sharedBirthContext.timezoneOffset = data.timezone?.timezone_offset || sharedBirthContext.timezoneOffset;
      sharedBirthContext.timezoneResolvedOffset = data.timezone?.timezone_offset || sharedBirthContext.timezoneResolvedOffset;
      sharedBirthContext.timezoneName = data.timezone?.timezone_name || sharedBirthContext.timezoneName;
      renderSharedCurrentData();
      const llmUnavailableMessage = data.llm_message
        || "Карта рассчитана, но текстовая интерпретация сейчас недоступна. Попробуйте повторить позже.";
      if (data.llm_status === "unavailable" || data.horoscope_text == null) {
        horoscopeBoxEl.textContent = llmUnavailableMessage;
      } else {
        horoscopeBoxEl.textContent = data.horoscope_text;
      }
      renderExpertTables(data.chart_response, data.timezone, data.warnings);
      expertWrapEl.classList.add("hidden");
      toggleExpertBtnEl.textContent = "Показать экспертную таблицу";
      apiRawBoxEl.textContent = JSON.stringify(data.chart_response, null, 2);
      apiRawWrapEl.classList.add("hidden");
      toggleApiRawBtnEl.textContent = "Показать ответ API целиком";
      modalEl.classList.add("active");
      const tz = data.timezone || {};
      const tzInfo = tz.timezone_source === "manual_offset"
        ? `Часовой пояс указан вручную: ${tz.timezone_offset || body.timezone_offset}`
        : `Часовой пояс определён автоматически: ${tz.timezone_name || timezoneNameEl.value || "n/a"}, ${tz.timezone_offset || ""}`;
      const userWarnings = Array.isArray(data.warnings)
        ? (
          data.llm_status === "unavailable"
            ? data.warnings.filter((item) => item !== "llm_unavailable")
            : data.warnings
        )
        : [];
      const warnText = userWarnings.length
        ? formatWarnings(userWarnings)
        : "";
      if (data.llm_status === "unavailable") {
        setStatus(`Готово. UTC: ${data.datetime_utc}. ${tzInfo} ${llmUnavailableMessage}${warnText}`);
      } else {
        setStatus(`Готово. UTC: ${data.datetime_utc}. ${tzInfo}${warnText}`);
      }
    }

    export function renderRectIntervals(intervals) {
      rectIntervalsListEl.innerHTML = "";
      if (!intervals || !intervals.length) {
        rectIntervalsListEl.innerHTML = "<div class='interval-item'>Интервалы не найдены.</div>";
        return;
      }
      intervals.forEach((item) => {
        const block = document.createElement("div");
        block.className = "interval-item";
        const sign = `${item.sign_name_ru || item.sign_name_en} (${item.sign_name_en})`;
        block.textContent = `#${item.interval_index}: ${sign} | ${item.start_local} → ${item.end_local} | ${item.duration_minutes} мин`;
        rectIntervalsListEl.appendChild(block);
      });
    }

    export async function runRectification() {
      syncSharedBirthContext(getRectContextPatch(), { silent: false });
      setRectStatus("Считаем интервалы...");
      const zodiacMode = rectZodiacModeEl.value;
      const sidMode = rectSiderealModeEl.value || null;
      const body = {
        api_base_url: document.getElementById("rectApiBaseUrl").value.trim(),
        birth_date_local: document.getElementById("rectBirthDate").value,
        latitude: Number(document.getElementById("rectLatitude").value),
        longitude: Number(document.getElementById("rectLongitude").value),
        house_system: document.getElementById("rectHouseSystem").value,
        zodiac_mode: zodiacMode,
        sidereal_mode: zodiacMode === "sidereal" ? sidMode : null,
      };
      const res = await fetch("/api/rectification/asc-sign-intervals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setRectStatus("Ошибка: " + extractErrorText(data));
        rectIntervalsListEl.innerHTML = "";
        rectJsonBoxEl.textContent = "";
        return;
      }
      renderRectIntervals(data.asc_sign_intervals || []);
      rectJsonBoxEl.textContent = JSON.stringify(data, null, 2);
      setRectStatus(`Готово. Найдено интервалов: ${(data.asc_sign_intervals || []).length}`);
    }
