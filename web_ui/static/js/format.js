// Авто-извлечено из main.js — чистые форматтеры (строки/HTML-строки).
import { PRO_METHOD_LABELS, PRO_EVENT_TYPE_LABELS } from "./constants.js";

    export function formatNum(value, digits = 2) {
      if (typeof value !== "number" || Number.isNaN(value)) return "—";
      return value.toFixed(digits);
    }

    export function formatLocalDateTimeCompact(localIso) {
      if (typeof localIso !== "string" || !localIso) return "";
      const dt = new Date(localIso);
      if (Number.isNaN(dt.getTime())) return localIso;
      const dd = String(dt.getDate()).padStart(2, "0");
      const mm = String(dt.getMonth() + 1).padStart(2, "0");
      const yyyy = dt.getFullYear();
      const hh = String(dt.getHours()).padStart(2, "0");
      const min = String(dt.getMinutes()).padStart(2, "0");
      return `${dd}.${mm}.${yyyy} ${hh}:${min}`;
    }

    export function formatIntervalLine(startLocal, endLocal) {
      if (!startLocal || !endLocal) return `${startLocal || ""} → ${endLocal || ""}`;
      const start = new Date(startLocal);
      const end = new Date(endLocal);
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
        return `${startLocal} → ${endLocal}`;
      }
      const sdd = String(start.getDate()).padStart(2, "0");
      const smm = String(start.getMonth() + 1).padStart(2, "0");
      const syyyy = start.getFullYear();
      const shh = String(start.getHours()).padStart(2, "0");
      const smin = String(start.getMinutes()).padStart(2, "0");
      const ehh = String(end.getHours()).padStart(2, "0");
      const emin = String(end.getMinutes()).padStart(2, "0");
      const sameDate =
        start.getFullYear() === end.getFullYear() &&
        start.getMonth() === end.getMonth() &&
        start.getDate() === end.getDate();
      if (sameDate) {
        return `${sdd}.${smm}.${syyyy} ${shh}:${smin}–${ehh}:${emin}`;
      }
      const edd = String(end.getDate()).padStart(2, "0");
      const emm = String(end.getMonth() + 1).padStart(2, "0");
      const eyyyy = end.getFullYear();
      return `${sdd}.${smm}.${syyyy} ${shh}:${smin} → ${edd}.${emm}.${eyyyy} ${ehh}:${emin}`;
    }

    export function degreeToDms(value, includeSeconds = false) {
      if (typeof value !== "number" || Number.isNaN(value)) return "—";
      const normalized = ((value % 360) + 360) % 360;
      const wholeDegrees = Math.floor(normalized);
      const minutesFull = (normalized - wholeDegrees) * 60;
      let wholeMinutes = Math.floor(minutesFull);
      let seconds = Math.round((minutesFull - wholeMinutes) * 60);
      let degreesAdjusted = wholeDegrees;

      if (seconds === 60) {
        seconds = 0;
        wholeMinutes += 1;
      }
      if (wholeMinutes === 60) {
        wholeMinutes = 0;
        degreesAdjusted += 1;
      }

      if (!includeSeconds) {
        return `${degreesAdjusted}°${String(wholeMinutes).padStart(2, "0")}′`;
      }
      return `${degreesAdjusted}°${String(wholeMinutes).padStart(2, "0")}′${String(seconds).padStart(2, "0")}″`;
    }

    export function resolveMotionPhase(obj) {
      const speed = typeof obj?.speed_longitude_deg_per_day === "number"
        ? obj.speed_longitude_deg_per_day
        : null;
      if (speed === null || !Number.isFinite(speed)) {
        return "D";
      }
      const stationaryThreshold = 0.0002;
      if (Math.abs(speed) <= stationaryThreshold) {
        return "S";
      }
      return speed < 0 ? "R" : "D";
    }

    export function renderTable(headers, rows) {
      if (!rows.length) {
        return "<div class='hint'>Нет данных.</div>";
      }
      const th = headers.map((h) => `<th>${h}</th>`).join("");
      const tr = rows
        .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
        .join("");
      return `<table class="expert-table"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
    }

    export function resolveAspectStrengthLabel(aspect) {
      const orb = Number(aspect?.orb);
      if (!Number.isFinite(orb)) return "—";
      if (orb <= 0.5) return "exact";
      if (orb <= 1.5) return "strong";
      if (orb <= 3.0) return "working";
      return "weak";
    }

    export function extractErrorText(payload) {
      if (!payload) return "Unknown error";
      if (typeof payload === "string") return payload;
      const detail = payload.detail || payload.error || payload;
      if (typeof detail?.user_message === "string" && detail.user_message.trim()) {
        return detail.user_message;
      }
      const upstreamStatus = detail?.status_code || payload.status_code;
      const rawError = typeof detail?.raw_error === "string"
        ? detail.raw_error
        : (typeof detail?.body === "string" ? detail.body : "");
      if (upstreamStatus === 402 && rawError) {
        return "Карта рассчитана, но текстовая интерпретация сейчас недоступна. Попробуйте повторить позже.";
      }
      if (upstreamStatus === 401 || upstreamStatus === 403) {
        return "Не удалось авторизоваться в сервисе модели. Обратитесь к администратору.";
      }
      if (upstreamStatus === 429) {
        return "Сервис модели перегружен. Повторите попытку чуть позже.";
      }
      if (upstreamStatus === 500 || upstreamStatus === 503) {
        return "Сервис модели временно недоступен. Попробуйте ещё раз позже.";
      }
      if (payload.detail) {
        if (typeof payload.detail === "string") return payload.detail;
        return JSON.stringify(payload.detail, null, 2);
      }
      if (payload.error && payload.error.message) return payload.error.message;
      return JSON.stringify(payload, null, 2);
    }

    export function humanizeNonJsonError(res, text) {
      const safeText = typeof text === "string" ? text : "";
      const normalized = safeText.toLowerCase();
      if (res?.status === 504 || normalized.includes("gateway time-out") || normalized.includes("gateway timeout")) {
        return "Расчёт занял слишком много времени. Попробуйте меньше событий или Beta/V1 режим.";
      }
      if (res?.status === 502 || normalized.includes("temporary failure in name resolution")) {
        return "Сервис Pro-ректификации временно недоступен. Попробуйте повторить позже.";
      }
      if (normalized.includes("<html") || normalized.includes("<!doctype html")) {
        return "Сервис временно недоступен. Попробуйте повторить позже.";
      }
      return safeText || "empty response body";
    }

    export function getHeavyProRunWarning(payload) {
      const eventsCount = Array.isArray(payload?.events) ? payload.events.length : 0;
      const formulaCardId = String(payload?.settings?.formula_card_id || "");
      const isV2Card = formulaCardId.endsWith("_002_DRAFT");
      const isComparison = Array.isArray(payload?.settings?.compare_formula_card_ids)
        && payload.settings.compare_formula_card_ids.length > 1;
      if ((isV2Card || isComparison) && eventsCount >= 4) {
        return "V2 comparison may take up to 2 minutes.";
      }
      return "";
    }

    export function normalizeLlmReason(reason) {
      const map = {
        insufficient_credits_or_max_tokens: "insufficient_credits_or_max_tokens",
        unauthorized_or_forbidden: "unauthorized_or_forbidden",
        rate_limited: "rate_limited",
        provider_unavailable: "provider_unavailable",
      };
      return map[reason] || reason || null;
    }

    export function formatWarnings(warnings) {
      if (!Array.isArray(warnings) || !warnings.length) {
        return "";
      }
      const mapping = {
        llm_request_failed: "Ответ модели не получен, поэтому использован резервный расчёт по вашим ответам.",
        llm_generation_fallback_used: "Ответ модели не получен, поэтому показан резервный краткий разбор.",
        llm_unavailable: "Карта рассчитана, но текстовая интерпретация сейчас недоступна. Попробуйте повторить позже.",
        invalid_llm_json: "Модель вернула некорректный ответ. Использован резервный сценарий.",
        missing_options: "Модель не вернула варианты ответа. Использован резервный вопрос.",
        fallback_question_used: "Задан уточняющий вопрос из резервного сценария.",
        min_questions_not_reached: "Для надёжного вывода нужно ответить ещё на несколько вопросов.",
        sign_scores_are_close: "Кандидаты Asc близки по баллам. Требуется проверка через события жизни.",
        element_scores_are_close: "Стихии близки по оценке. Нужны дополнительные уточнения.",
        modality_scores_are_close: "Крест близок по оценке. Нужны дополнительные уточнения.",
        technical_fallback_used: "Применён резервный расчёт из-за ограничений входных данных.",
        sequence_number_required_retry: "Для повторяемого события укажите, какой это случай по счёту.",
        repeatable_event_collect_more: "Продолжаем сбор повторяемого события по указанному количеству.",
      };
      const known = warnings
        .map((item) => mapping[item])
        .filter(Boolean);
      const hasUnknown = warnings.some((item) => !mapping[item]);
      if (hasUnknown) {
        known.push("Есть служебные предупреждения. Подробности доступны в техническом режиме.");
      }
      const text = known.join(" ");
      return text ? ` ${text}` : "";
    }

    export function formatElapsedDuration(seconds) {
      if (seconds < 60) {
        return `${seconds} сек`;
      }
      const minutes = Math.floor(seconds / 60);
      const restSeconds = seconds % 60;
      return `${minutes} мин ${restSeconds} сек`;
    }

    export function formatUsage(usage) {
      return {
        input_tokens: usage?.input_tokens ?? null,
        output_tokens: usage?.output_tokens ?? null,
        total_tokens: usage?.total_tokens ?? null,
        cached_input_tokens: usage?.cached_input_tokens ?? null,
        reasoning_tokens: usage?.reasoning_tokens ?? null,
      };
    }

    export function formatCandidateGroupText(candidateGroup) {
      if (!candidateGroup || !Array.isArray(candidateGroup.signs) || !candidateGroup.signs.length) {
        return "";
      }
      const signLabelMap = {
        Aries: "Овен",
        Taurus: "Телец",
        Gemini: "Близнецы",
        Cancer: "Рак",
        Leo: "Лев",
        Virgo: "Дева",
        Libra: "Весы",
        Scorpio: "Скорпион",
        Sagittarius: "Стрелец",
        Capricorn: "Козерог",
        Aquarius: "Водолей",
        Pisces: "Рыбы",
      };
      const elementLabelMap = {
        fire: "Огонь",
        earth: "Земля",
        air: "Воздух",
        water: "Вода",
      };
      const modalityLabelMap = {
        cardinal: "кардинальный",
        fixed: "фиксированный",
        mutable: "мутабельный",
      };
      const signsText = candidateGroup.signs.map((sign) => signLabelMap[sign] || sign).join(", ");
      const elementText = candidateGroup.element ? (elementLabelMap[candidateGroup.element] || candidateGroup.element) : "смешанная";
      const modalityText = candidateGroup.modality
        ? (modalityLabelMap[candidateGroup.modality] || candidateGroup.modality)
        : "не определён";
      return `Стихия: ${elementText}. Крест: ${modalityText}. Кандидаты: ${signsText}. Для точного выбора знака нужны дополнительные вопросы.`;
    }

    export function formatStage1SecondaryCandidatesHtml(candidates) {
      if (!Array.isArray(candidates) || !candidates.length) {
        return "нет";
      }
      const lines = candidates.map((candidate) => {
        const ranges = Array.isArray(candidate.time_ranges_local) && candidate.time_ranges_local.length
          ? candidate.time_ranges_local
          : (candidate.time_range_local ? [candidate.time_range_local] : []);
        const rangeText = ranges.length
          ? ranges.map((r, i) => `${i + 1}) ${formatIntervalLine(r.start, r.end)}`).join("<br/>")
          : "интервалы не указаны";
        return (
          `<div style="margin-bottom:8px;">` +
          `<div><strong>${candidate.sign_name_ru || candidate.sign_name_en || "Кандидат"}</strong> ` +
          `(${candidate.sign_name_en || "—"}) — ${candidate.probability ?? "n/a"}</div>` +
          `<div>Интервалы:<br/>${rangeText}</div>` +
          `</div>`
        );
      });
      return lines.join("");
    }

    export function formatMethodLabel(methodName) {
      return PRO_METHOD_LABELS[methodName] || methodName || "Метод";
    }

    export function formatEventTypeLabel(eventType) {
      return PRO_EVENT_TYPE_LABELS[eventType] || eventType || "событие";
    }

    export function formatOrbValue(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "—";
      return `${n.toFixed(2)}°`;
    }

    export function extractProMatchDetails(match) {
      if (!match || typeof match !== "object") {
        return {
          aspect: "—",
          orb: "—",
          points: "—",
          score: "—",
          explanation: "Совпадений по сигналам метода не найдено.",
        };
      }

      const aspect = match.aspect_type || "—";
      const orb = formatOrbValue(match.orb);
      const scoreNum = Number(match.score);
      const score = Number.isFinite(scoreNum) ? scoreNum.toFixed(2) : "—";
      const explanation = match.explanation || "Технически подтверждено сигналом метода, требуется экспертная проверка.";

      let points = "—";
      if (match.directed_object || match.natal_object) {
        points = `${match.directed_object || "—"} ↔ ${match.natal_object || "—"}`;
      } else if (match.transit_object || match.natal_object) {
        points = `${match.transit_object || "—"} ↔ ${match.natal_object || "—"}`;
      } else if (match.solar_point || match.target) {
        points = `${match.solar_point || "—"} ↔ ${match.target || "—"}`;
      } else if (match.asc_sign || Number.isFinite(Number(match.degree_in_sign))) {
        points = `${match.asc_sign || "—"} ${Number.isFinite(Number(match.degree_in_sign)) ? `${match.degree_in_sign}°` : ""}`.trim();
      }

      return { aspect, orb, points, score, explanation };
    }

    export function formatJsonCompact(value) {
      if (!value || typeof value !== "object") return "не рассчитано";
      try {
        return JSON.stringify(value);
      } catch (err) {
        return "не рассчитано";
      }
    }

    export function formatPriorityCounts(priorityCounts) {
      const counts = priorityCounts || {};
      return `golden=${counts.golden ?? 0}, supporting=${counts.supporting ?? 0}, context=${counts.context ?? 0}, ambiguity_risk=${counts.ambiguity_risk ?? 0}`;
    }

    export function formatRuleListCompact(rules, limit = 8) {
      const list = Array.isArray(rules) ? rules : [];
      if (!list.length) return "none";
      const visible = list.slice(0, limit).map((item) => {
        if (typeof item === "string") return item;
        const formula = item?.display_formula || item?.formula || item?.id || "—";
        const inherited = item?.inherited_from_v1 ? " [inherited_from_v1]" : "";
        return `${formula}${inherited}`;
      });
      const suffix = list.length > limit ? ` (+${list.length - limit} more)` : "";
      return `${visible.join("; ")}${suffix}`;
    }

    export function formatRejectedReasonsCompact(reasons) {
      const list = Array.isArray(reasons) ? reasons : [];
      if (!list.length) return "none";
      return list.map((item) => `${item.reason || "unknown"}=${item.count ?? 0}`).join(", ");
    }

    export function formatUnresolvedSummaryCompact(reasons) {
      const list = Array.isArray(reasons) ? reasons : [];
      if (!list.length) return "none";
      return list.map((item) => `${item.reason || "unknown"}=${item.count ?? 0}`).join(", ");
    }

