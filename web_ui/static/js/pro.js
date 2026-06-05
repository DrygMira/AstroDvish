// Авто-извлечено из main.js (build-split). Модуль: pro.
import { expertWrapEl, horoscopeBoxEl, modalEl, rdSiderealModeEl, rdZodiacModeEl, rpBestCandidatesEl, rpCompareV1V2El, rpConfidenceEl, rpExplainBodyEl, rpFormulaCardIdEl, rpFormulaComparisonEl, rpFormulaMultiCardEl, rpMethodsSummaryEl, rpUseAllRelevantV2CardsEl, rpWarningsEl, timezoneModeEl, timezoneNameEl, timezoneOffsetEl, toggleExpertBtnEl } from "./dom.js";
import { appState, rectDialogState, rectEventsState, rectificationWizardState, sharedBirthContext } from "./state.js";
import { normalizeProEventCard } from "./validation.js";
import { extractProMatchDetails, formatEventTypeLabel, formatJsonCompact, formatMethodLabel, formatPriorityCounts, formatRejectedReasonsCompact, formatRuleListCompact, formatUnresolvedSummaryCompact, getHeavyProRunWarning, renderTable } from "./format.js";
import { fetchWithTimeout, parseResponseBody } from "./api.js";
import { buildFormulaAspectRows, buildFormulaPointDebugRows, buildFormulaRuleStatusRows, renderExpertTables } from "./chart.js";
import { renderRectEventsFinal } from "./stage2.js";
import { hideLlmOverlay, setReStatus, setRpStatus, setStatus, setTab, setTechnicalMode, setWzProStatus, setWzStatus, showLlmOverlay } from "./ui.js";
import { renderWizardProgress, updateWizardContextFromCurrentStates } from "./wizard.js";

    function resolveComparisonCardIds(selectedCardId) {
      const normalized = String(selectedCardId || "").trim();
      const pairs = {
        RECT_CHILD_BIRTH_002_DRAFT: ["RECT_CHILD_BIRTH_001", "RECT_CHILD_BIRTH_002_DRAFT"],
        RECT_MARRIAGE_UNION_002_DRAFT: ["RECT_MARRIAGE_UNION_001", "RECT_MARRIAGE_UNION_002_DRAFT"],
      };
      return pairs[normalized] || [];
    }

    function resolveRelevantV2DraftCardIds(events) {
      const list = Array.isArray(events) ? events : [];
      const selected = [];
      const push = (cardId) => {
        if (cardId && !selected.includes(cardId)) selected.push(cardId);
      };
      list.forEach((event) => {
        const eventType = String(event?.event_type || "").trim();
        if (eventType === "child_birth" || eventType === "children_birth") {
          push("RECT_CHILD_BIRTH_002_DRAFT");
        }
        if (eventType === "marriage_start" || eventType === "marriage_union") {
          push("RECT_MARRIAGE_UNION_002_DRAFT");
        }
        if (eventType === "profession_change") {
          push("RECT_PROFESSION_CHANGE_002_DRAFT");
        }
      });
      return selected;
    }

    export function buildProAscWindowsFromStage1() {
      const lastFinal = [...rectDialogState.dialogHistory]
        .reverse()
        .find((x) => x.role === "assistant" && x.type === "final_result");
      if (!lastFinal) {
        const intervals = rectDialogState.rectificationDocument?.asc_sign_intervals;
        if (!Array.isArray(intervals) || !intervals.length) {
          return [];
        }
        return intervals.map((item) => ({
          start_local: item.start_local,
          end_local: item.end_local,
          sign_name_en: item.sign_name_en,
          sign_name_ru: item.sign_name_ru || null,
        }));
      }

      const candidates = [
        lastFinal.primary_candidate,
        ...((Array.isArray(lastFinal.secondary_candidates) ? lastFinal.secondary_candidates : [])),
      ].filter(Boolean);

      const windows = [];
      candidates.forEach((candidate) => {
        const ranges = Array.isArray(candidate.time_ranges_local) && candidate.time_ranges_local.length
          ? candidate.time_ranges_local
          : (candidate.time_range_local ? [candidate.time_range_local] : []);
        ranges.forEach((r) => {
          if (!r?.start || !r?.end) return;
          windows.push({
            start_local: r.start,
            end_local: r.end,
            sign_name_en: candidate.sign_name_en || "Unknown",
            sign_name_ru: candidate.sign_name_ru || null,
          });
        });
      });
      return windows;
    }

    export function buildProEventsFromStage2() {
      const events = rectEventsState.finalized && Array.isArray(rectEventsState.finalized.events)
        ? rectEventsState.finalized.events
        : [];
      return events
        .map((event, idx) => normalizeProEventCard(event, idx))
        .filter(Boolean);
    }

    export function buildProTestEventsPreset() {
      return [
        {
          event_id: "preset_ev_1",
          event_type: "marriage_start",
          title: "Оформление брака",
          date_text: "2012-08-18",
          start_date: "2012-08-18",
          end_date: "2012-08-18",
          date_precision: "exact",
          impact_level: 5,
          reversibility: "reversible",
          life_area: "relationships",
          sequence_number: 1,
          notes: "Тестовый пресет для E2E Pro",
          user_skipped: false,
        },
        {
          event_id: "preset_ev_2",
          event_type: "long_distance_relocation",
          title: "Переезд",
          date_text: "2016-05",
          start_date: "2016-05-01",
          end_date: "2016-05-31",
          date_precision: "month",
          impact_level: 4,
          reversibility: "irreversible",
          life_area: "home",
          sequence_number: 1,
          notes: "Тестовый пресет для E2E Pro",
          user_skipped: false,
        },
        {
          event_id: "preset_ev_3",
          event_type: "child_birth",
          title: "Рождение первого ребёнка",
          date_text: "2018-09-12",
          start_date: "2018-09-12",
          end_date: "2018-09-12",
          date_precision: "exact",
          impact_level: 5,
          reversibility: "irreversible",
          life_area: "family",
          sequence_number: 1,
          notes: "Тестовый пресет для E2E Pro",
          user_skipped: false,
        },
      ];
    }

    export function applyProTestEventsPreset() {
      const presetEvents = buildProTestEventsPreset()
        .map((event, idx) => normalizeProEventCard(event, idx))
        .filter(Boolean);
      rectEventsState.finalized = {
        status: "finalized",
        step_index: rectEventsState.finalized?.step_index || 99,
        events_collected_count: presetEvents.length,
        warnings: ["test_events_preset_applied"],
        events: presetEvents,
        events_count: presetEvents.length,
        strong_events_count: presetEvents.filter((event) => (event.impact_level || 0) >= 4).length,
        confidence_preliminary: "medium",
        dialog_history: rectEventsState.dialogHistory || [],
      };
      renderRectEventsFinal(rectEventsState.finalized);
      updateWizardContextFromCurrentStates();
      setReStatus("Тестовые события для Pro добавлены.");
      setWzStatus("Тестовые события для Pro добавлены в Stage 2.");
    }

    export function buildProEventMap() {
      const events = buildProEventsFromStage2();
      const map = new Map();
      events.forEach((event) => {
        if (event?.event_id) map.set(event.event_id, event);
      });
      return map;
    }

    export function summarizeMethodStats(methodResults) {
      const normalized = {};
      Object.entries(methodResults || {}).forEach(([methodName, rawEntries]) => {
        const entries = Array.isArray(rawEntries) ? rawEntries : [];
        const matched = entries.filter((entry) => Array.isArray(entry?.matches) && entry.matches.length > 0).length;
        normalized[methodName] = { entriesCount: entries.length, matchedCount: matched };
      });
      return normalized;
    }

    export function isMethodInactive(stats, methodName) {
      const item = stats?.[methodName];
      if (!item) return true;
      return Number(item.entriesCount || 0) === 0 && Number(item.matchedCount || 0) === 0;
    }

    export function getStage2RepeatCountHint(eventType, sequenceNumber) {
      const history = Array.isArray(rectEventsState.dialogHistory) ? rectEventsState.dialogHistory : [];
      for (const item of history) {
        if (!item || item.role !== "user") continue;
        if (item.event_type !== eventType) continue;
        const raw = item.raw_answer || {};
        if (sequenceNumber != null && Number(raw.sequence_number) !== Number(sequenceNumber)) continue;
        const repeatCount = Number(raw.repeat_count);
        if (Number.isFinite(repeatCount) && repeatCount >= 1) return repeatCount;
      }
      return null;
    }

    export function buildProExplainabilityHtml(data) {
      const chartResponse = appState.lastExpertRenderPayload?.chartResponse || null;
      const timezoneFromChart = appState.lastExpertRenderPayload?.timezonePayload || null;
      const proPayload = appState.lastProRunPayload || {};
      const methodStats = summarizeMethodStats(data?.method_results || {});
      const eventsUsed = Array.isArray(proPayload.events) ? proPayload.events : buildProEventsFromStage2();
      const bestWindows = Array.isArray(data?.best_candidates) ? data.best_candidates : [];
      const stage1 = rectificationWizardState.stage1 || {};
      const stageWarnings = Array.isArray(stage1.stageWarnings) ? stage1.stageWarnings : [];
      const closeCandidates = stageWarnings.includes("sign_scores_are_close")
        || stageWarnings.includes("element_scores_are_close")
        || stageWarnings.includes("modality_scores_are_close");

      const mainMethods = ["directions", "solars", "transits"];
      const methodsUsed = mainMethods
        .filter((name) => !isMethodInactive(methodStats, name))
        .map((name) => `${formatMethodLabel(name)}: записей ${methodStats[name].entriesCount}, подтверждений ${methodStats[name].matchedCount}`);
      const inactiveOptionalMethods = ["lunars", "totems"]
        .filter((name) => isMethodInactive(methodStats, name))
        .map((name) => formatMethodLabel(name));

      const chartObjects = chartResponse?.objects || {};
      const objectNames = Object.keys(chartObjects);
      const trueNorthNode = chartObjects.true_north_node || null;
      const trueSouthNode = chartObjects.true_south_node || null;
      const houses = chartResponse?.houses?.cusp_details || {};
      const aspects = Array.isArray(chartResponse?.aspects) ? chartResponse.aspects : [];
      const planetHouseCount = objectNames.filter((name) => chartObjects[name]?.house != null).length;

      const primaryCandidate = stage1.primaryCandidate || null;
      const primaryRanges = Array.isArray(primaryCandidate?.time_ranges_local) && primaryCandidate.time_ranges_local.length
        ? primaryCandidate.time_ranges_local
        : (primaryCandidate?.time_range_local ? [primaryCandidate.time_range_local] : []);
      const secondaryCandidates = Array.isArray(stage1.secondaryCandidates) ? stage1.secondaryCandidates : [];

      const explainRows = [];
      explainRows.push("<div><strong>1) Система использовала следующие данные</strong></div>");
      explainRows.push(`<div>Дата рождения: ${proPayload.birth_date_local || sharedBirthContext.birthDateLocal || "не рассчитано"}</div>`);
      explainRows.push(`<div>Время рождения (HH:MM:SS): ${sharedBirthContext.birthDateTimeLocal || "не рассчитано"}</div>`);
      explainRows.push(`<div>Место: ${sharedBirthContext.selectedPlaceLabel || sharedBirthContext.cityQuery || rectificationWizardState.birthPlace || "не рассчитано"}</div>`);
      explainRows.push(`<div>Координаты: ${proPayload.latitude ?? sharedBirthContext.latitude ?? "не рассчитано"}, ${proPayload.longitude ?? sharedBirthContext.longitude ?? "не рассчитано"}</div>`);
      explainRows.push(`<div>DMS: ${sharedBirthContext.latitudeDms || "не рассчитано"}, ${sharedBirthContext.longitudeDms || "не рассчитано"}</div>`);
      explainRows.push(`<div>Timezone: ${proPayload.timezone_name || sharedBirthContext.timezoneName || "не рассчитано"} (${sharedBirthContext.timezoneMode || "не рассчитано"})</div>`);
      explainRows.push(`<div>House system: ${proPayload.house_system || sharedBirthContext.houseSystem || "не рассчитано"}</div>`);
      explainRows.push(`<div>Zodiac: ${proPayload.zodiac_mode || sharedBirthContext.zodiacMode || "не рассчитано"}</div>`);

      explainRows.push("<div style='margin-top:8px;'><strong>2) Данные карты, использованные в проверке</strong></div>");
      explainRows.push(`<div>Asc: ${chartResponse?.angles?.asc ?? "не рассчитано"} | MC: ${chartResponse?.angles?.mc ?? "не рассчитано"}</div>`);
      explainRows.push(`<div>Куспиды домов: ${Object.keys(houses).length || 0}</div>`);
      explainRows.push(`<div>Планеты/объекты: ${objectNames.length}</div>`);
      explainRows.push(`<div>Истинный северный узел: ${trueNorthNode ? `${trueNorthNode.sign_name_en || "—"} ${trueNorthNode.sign_degree_dms || "—"}` : "не рассчитано"}</div>`);
      explainRows.push(`<div>Истинный южный узел: ${trueSouthNode ? `${trueSouthNode.sign_name_en || "—"} ${trueSouthNode.sign_degree_dms || "—"}` : "не рассчитано"}</div>`);
      explainRows.push(`<div>Планеты с определённым домом: ${planetHouseCount}</div>`);
      explainRows.push(`<div>Аспекты в chart_response: ${aspects.length}</div>`);
      explainRows.push(`<div>Timezone блока расчёта: ${formatJsonCompact(timezoneFromChart)}</div>`);

      explainRows.push("<div style='margin-top:8px;'><strong>3) Логика Stage 1</strong></div>");
      explainRows.push(`<div>Element scores: ${formatJsonCompact(stage1.elementScores)}</div>`);
      explainRows.push(`<div>Cross/Modality scores: ${formatJsonCompact(stage1.modalityScores)}</div>`);
      explainRows.push(`<div>Основной Asc-кандидат: ${primaryCandidate ? `${primaryCandidate.sign_name_ru || primaryCandidate.sign_name_en || "—"} (${primaryCandidate.probability ?? "n/a"})` : "не рассчитано"}</div>`);
      explainRows.push(`<div>Вторичные кандидаты: ${secondaryCandidates.length ? secondaryCandidates.map((item) => `${item.sign_name_ru || item.sign_name_en || "—"} (${item.probability ?? "n/a"})`).join("; ") : "не рассчитано"}</div>`);
      explainRows.push(`<div>Почему выбран кандидат: ${stage1.explanationText || stage1.summaryText || "не рассчитано"}</div>`);
      explainRows.push(`<div>Кандидаты близки: ${closeCandidates ? "да, результат Stage 1 не финальный" : "нет"}</div>`);

      explainRows.push("<div style='margin-top:8px;'><strong>4) Окна кандидатов и Pro-ранжирование</strong></div>");
      explainRows.push(`<div>Primary Asc windows: ${primaryRanges.length ? primaryRanges.map((item) => `${item.start} → ${item.end}`).join("; ") : "не рассчитано"}</div>`);
      const secondaryRanges = secondaryCandidates
        .flatMap((candidate) => Array.isArray(candidate.time_ranges_local) ? candidate.time_ranges_local : [])
        .map((item) => `${item.start} → ${item.end}`);
      explainRows.push(`<div>Secondary Asc windows: ${secondaryRanges.length ? secondaryRanges.join("; ") : "не рассчитано"}</div>`);
      if (!bestWindows.length) {
        explainRows.push("<div>Best Pro windows: не рассчитано</div>");
      } else {
        bestWindows.forEach((item, idx) => {
          const clipped = item.clipped_by_birth_date ? "да" : "нет";
          explainRows.push(
            `<div>#${idx + 1}: ${item.candidate_window?.start || "—"} → ${item.candidate_window?.end || "—"} | total=${item.scores?.total ?? "n/a"} | confidence=${item.confidence_level || "n/a"} | clipped=${clipped}</div>`
          );
        });
      }
      explainRows.push("<div>Ширина окна: это диапазон поиска, а не точное время рождения.</div>");

      explainRows.push("<div style='margin-top:8px;'><strong>5) События, переданные в Pro</strong></div>");
      if (!eventsUsed.length) {
        explainRows.push("<div>События: не рассчитано</div>");
      } else {
        eventsUsed.forEach((event, idx) => {
          const repeatCount = getStage2RepeatCountHint(event.event_type, event.sequence_number);
          explainRows.push(
            `<div>#${idx + 1}: ${event.title || "Событие"} | type=${event.event_type || "—"} | date=${event.date_text || event.start_date || "—"} | precision=${event.date_precision || "—"} | seq=${event.sequence_number ?? "—"} | impact=${event.impact_level ?? "—"} | life_area=${event.life_area || "—"} | repeat_count=${repeatCount ?? "не рассчитано"}</div>`
          );
        });
      }

      explainRows.push("<div style='margin-top:8px;'><strong>6) Методы, использованные в текущем расчёте</strong></div>");
      explainRows.push(`<div>${methodsUsed.length ? methodsUsed.join(" | ") : "не рассчитано"}</div>`);
      explainRows.push(`<div>Скрыто в основном UI как неактивные: ${inactiveOptionalMethods.length ? inactiveOptionalMethods.join(", ") : "нет"}</div>`);

      const topWindow = bestWindows[0] || null;
      const confidence = data?.confidence || {};
      explainRows.push("<div style='margin-top:8px;'><strong>7) Почему выбран итоговый диапазон</strong></div>");
      explainRows.push(`<div>Это окно получило больше подтверждений, потому что total score=${topWindow?.scores?.total ?? "n/a"} и подтверждённых событий ${topWindow?.matched_events_count ?? "n/a"}.</div>`);
      explainRows.push(`<div>Текущий уровень уверенности: ${confidence.level || "не рассчитано"} (${confidence.explanation || "пояснение не рассчитано"}).</div>`);
      explainRows.push("<div>Метод пока является промежуточной проверкой, не финальным Direction Formula Engine.</div>");
      explainRows.push(`<div>Недостаточно данных: ${Array.isArray(data?.limitations) && data.limitations.length ? data.limitations.join(" | ") : "не рассчитано"}</div>`);
      explainRows.push(`<div>Неиспользованные данные/методы: ${inactiveOptionalMethods.length ? inactiveOptionalMethods.join(", ") : "нет"}</div>`);

      return explainRows.join("");
    }

    export function renderFormulaTestModeConfirmations(data) {
      const formulaResults = Array.isArray(data?.formula_test_mode_results) ? data.formula_test_mode_results : [];
      if (!formulaResults.length) return false;

      rpMethodsSummaryEl.innerHTML = "";
      formulaResults.forEach((result, idx) => {
        const report = result.validation_report || {};
        const matchedFormulaAspects = Array.isArray(result.matched_formula_aspects) ? result.matched_formula_aspects : [];
        const rejectedAspects = Array.isArray(result.rejected_aspects) ? result.rejected_aspects : [];
        const missingFormulaLinks = Array.isArray(result.missing_formula_links) ? result.missing_formula_links : [];
        const suspicious = Array.isArray(report.extra_or_suspicious_aspects) ? report.extra_or_suspicious_aspects : [];
        const scoreBreakdown = report.score_breakdown || {};
        const block = document.createElement("div");
        block.className = "interval-item";

        const titleNode = document.createElement("div");
        const titleStrong = document.createElement("strong");
        titleStrong.textContent = result.source_event_title || `Событие ${idx + 1}`;
        titleNode.appendChild(titleStrong);
        block.appendChild(titleNode);

        const lineTypeDate = document.createElement("div");
        lineTypeDate.textContent = `Тип: ${formatEventTypeLabel(result.source_event_type || result.event_type)} | Дата: ${result.source_event_date || "дата не указана"}`;
        block.appendChild(lineTypeDate);

        const lineCard = document.createElement("div");
        lineCard.textContent = `Card: ${result.card_id} | Version: ${result.card_version || "n/a"} | formulas_count=${result.formulas_count ?? "n/a"} | Status: ${report.final_status_for_expert || result.status || "n/a"} | Confidence: ${result.confidence || "n/a"} | Score: ${result.score ?? "n/a"}`;
        block.appendChild(lineCard);

        const linePriorityCounts = document.createElement("div");
        linePriorityCounts.className = "hint";
        linePriorityCounts.textContent = `priority_counts: ${formatPriorityCounts(result.priority_counts)} | context/ambiguity shown separately from golden/supporting`;
        block.appendChild(linePriorityCounts);

        const methodLine = document.createElement("div");
        methodLine.className = "hint";
        methodLine.textContent = `Direction method: ${result.debug?.direction_method_label || result.validation_report?.method_scope?.mvp_direction_method_label || result.debug?.direction_method || "n/a"}`;
        block.appendChild(methodLine);

        const tableLine = document.createElement("div");
        tableLine.className = "hint";
        tableLine.style.whiteSpace = "pre-wrap";
        tableLine.textContent = result.validation_report_table || "validation_report_table: не рассчитано";
        block.appendChild(tableLine);

        const expectedLine = document.createElement("div");
        expectedLine.textContent = `Expected: ${Array.isArray(report.expected_by_card?.direction_rules) ? report.expected_by_card.direction_rules.map((rule) => rule.display_formula || rule.id).join(", ") : "не рассчитано"}`;
        block.appendChild(expectedLine);

        const debugMetaLine = document.createElement("div");
        debugMetaLine.className = "hint";
        debugMetaLine.textContent = "rule_debug: rule-level Directed -> Natal checks with coordinates and orb diagnostics, including Source type, Target type, Resolved source group, Resolved target group, Include reason, Exclude reason, Ruler type, and closest_major_aspect_mismatch warnings.";
        block.appendChild(debugMetaLine);

        const debugHeader = document.createElement("div");
        debugHeader.style.marginTop = "8px";
        debugHeader.innerHTML = "<strong>Direction debug / Проверка дирекций</strong>";
        block.appendChild(debugHeader);

        const ruleRows = buildFormulaRuleStatusRows(result);
        const ruleTableWrap = document.createElement("div");
        ruleTableWrap.innerHTML = renderTable(
          [
            "Formula",
            "Priority",
            "Formula role",
            "Status",
            "Directed source",
            "Directed longitude",
            "Natal target",
            "Natal longitude",
            "Aspect",
            "Actual angle",
            "Exact angle",
            "Orb",
            "Orb limit",
            "Reject reason",
          ],
          ruleRows
        );
        block.appendChild(ruleTableWrap);

        const foundHeader = document.createElement("div");
        foundHeader.innerHTML = `<strong>matched_formula_aspects:</strong> ${matchedFormulaAspects.length}`;
        block.appendChild(foundHeader);
        if (!matchedFormulaAspects.length) {
          const noneLine = document.createElement("div");
          noneLine.textContent = "Найденных formula-specific аспектов нет.";
          block.appendChild(noneLine);
        } else {
          matchedFormulaAspects.forEach((match) => {
            const line = document.createElement("div");
            line.textContent = `${formatMethodLabel(match.method)} | ${match.directed_point} ${match.aspect_type} ${match.natal_target} | orb=${match.orb} | strength=${match.strength} | rule=${match.formula_rule_matched}`;
            block.appendChild(line);
            if (match.explanation_for_expert) {
              const exp = document.createElement("div");
              exp.className = "hint";
              exp.textContent = match.explanation_for_expert;
              block.appendChild(exp);
            }
          });
        }

        const matchedRows = buildFormulaAspectRows(matchedFormulaAspects);
        const matchedTableWrap = document.createElement("div");
        matchedTableWrap.innerHTML = renderTable(
          [
            "Rule",
            "Status",
            "Directed source",
            "Directed longitude",
            "Natal target",
            "Natal longitude",
            "Aspect",
            "Actual angle",
            "Exact angle",
            "Orb",
            "Orb limit",
            "Reject reason",
          ],
          matchedRows
        );
        block.appendChild(matchedTableWrap);

        const missedLine = document.createElement("div");
        missedLine.textContent = `Missing: ${missingFormulaLinks.length ? missingFormulaLinks.map((item) => item.display_formula || item.rule_id || "—").join(", ") : "нет"}`;
        block.appendChild(missedLine);

        const rejectedHeader = document.createElement("div");
        rejectedHeader.textContent = `Rejected: ${rejectedAspects.length}`;
        block.appendChild(rejectedHeader);
        const rejectedReasonCounts = {};
        rejectedAspects.forEach((match) => {
          const reasonKey = match.rejection_reason || match.reason || "unknown";
          rejectedReasonCounts[reasonKey] = (rejectedReasonCounts[reasonKey] || 0) + 1;
        });
        const rejectedReasonLine = document.createElement("div");
        rejectedReasonLine.className = "hint";
        rejectedReasonLine.textContent = `Top rejected reasons: ${Object.entries(rejectedReasonCounts).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([reason, count]) => `${reason}=${count}`).join(", ") || "none"}`;
        block.appendChild(rejectedReasonLine);
        rejectedAspects.slice(0, 5).forEach((match) => {
          const line = document.createElement("div");
          line.className = "hint";
          line.textContent = `${match.directed_point} ${match.aspect_type} ${match.natal_target} | orb=${match.orb} | reason=${match.rejection_reason || match.reason || "n/a"} | rule=${match.formula_rule_matched}`;
          block.appendChild(line);
        });
        if (rejectedAspects.length > 5) {
          const truncatedLine = document.createElement("div");
          truncatedLine.className = "hint";
          truncatedLine.textContent = `Main summary truncated: ${rejectedAspects.length - 5} more rejected aspects are available in raw/debug JSON.`;
          block.appendChild(truncatedLine);
        }

        if (rejectedAspects.length <= 20) {
          const rejectedRows = buildFormulaAspectRows(rejectedAspects);
          const rejectedTableWrap = document.createElement("div");
          rejectedTableWrap.innerHTML = renderTable(
            [
              "Rule",
              "Status",
              "Directed source",
              "Directed longitude",
              "Natal target",
              "Natal longitude",
              "Aspect",
              "Actual angle",
              "Exact angle",
              "Orb",
              "Orb limit",
              "Reject reason",
            ],
            rejectedRows
          );
          block.appendChild(rejectedTableWrap);
        }

        const directedPoints = Array.isArray(report.directed_points_debug) ? report.directed_points_debug : [];
        const directedHeader = document.createElement("div");
        directedHeader.style.marginTop = "8px";
        directedHeader.innerHTML = "<strong>directed_points_debug</strong>";
        block.appendChild(directedHeader);
        const directedWrap = document.createElement("div");
        directedWrap.innerHTML = renderTable(
          ["Point", "Natal longitude", "Directed longitude", "Direction arc"],
          buildFormulaPointDebugRows(directedPoints, true)
        );
        block.appendChild(directedWrap);

        const natalTargets = Array.isArray(report.natal_targets_debug) ? report.natal_targets_debug : [];
        const natalHeader = document.createElement("div");
        natalHeader.style.marginTop = "8px";
        natalHeader.innerHTML = "<strong>natal_targets_debug</strong>";
        block.appendChild(natalHeader);
        const natalWrap = document.createElement("div");
        natalWrap.innerHTML = renderTable(
          ["Point", "Natal longitude"],
          buildFormulaPointDebugRows(natalTargets, false)
        );
        block.appendChild(natalWrap);

        const suspiciousLine = document.createElement("div");
        suspiciousLine.textContent = `Suspicious: ${suspicious.length ? suspicious.map((item) => item.formula_rule_matched || item.aspect_type || "—").join(", ") : "нет"}`;
        block.appendChild(suspiciousLine);

        const scoreLine = document.createElement("div");
        scoreLine.className = "hint";
        scoreLine.textContent = `Score breakdown: core=${scoreBreakdown.matched_core_points ?? 0}, aspects=${scoreBreakdown.matched_aspect_points ?? 0}, formula=${scoreBreakdown.matched_formula_aspect_points ?? 0}, methods=${scoreBreakdown.method_points ?? 0}, penalty=${scoreBreakdown.exclusion_penalty ?? 0}`;
        block.appendChild(scoreLine);

        rpMethodsSummaryEl.appendChild(block);
      });
      return true;
    }

    export function renderFormulaCardComparison(data) {
      const comparison = data?.formula_card_comparison || null;
      rpFormulaComparisonEl.textContent = "";
      if (!comparison || !comparison.enabled) {
        rpFormulaComparisonEl.textContent = "V1 vs V2 comparison не запрошен.";
        return;
      }

      const items = Array.isArray(comparison.items) ? comparison.items : [];
      const differences = comparison.differences || {};
      const workingRangesDiff = Array.isArray(differences.working_time_ranges_difference)
        ? differences.working_time_ranges_difference
        : [];
      const bestCandidateDiff = differences.best_candidate_difference || {};
      const eventContributionDiff = differences.event_contribution_audit_difference || {};
      const sharedRules = Array.isArray(differences.shared_rules) ? differences.shared_rules : [];
      const v1OnlyRules = Array.isArray(differences.v1_only_rules) ? differences.v1_only_rules : [];
      const v2AddedRules = Array.isArray(differences.v2_added_rules) ? differences.v2_added_rules : [];
      const compactSummary = comparison.summary || {};
      const compactItems = Array.isArray(compactSummary.items) ? compactSummary.items : [];

      const lines = [
        `formula_card_comparison | baseline=${comparison.baseline_card_id || "n/a"} | selected=${comparison.selected_card_id || "n/a"}`,
      ];
      lines.push("Comparison summary");
      compactItems.forEach((item) => {
        const workingRange = item.working_range
          ? `${item.working_range.start_local || "n/a"} -> ${item.working_range.end_local || "n/a"}`
          : "n/a";
        lines.push(
          `${item.card_id} | formulas_count=${item.formulas_count ?? "n/a"} | working_range=${workingRange} | best_candidate=${item.best_candidate || "n/a"} | matched/rejected/missed=${item.matched ?? "n/a"}/${item.rejected ?? "n/a"}/${item.missed ?? "n/a"} | golden/supporting/context=${item.golden_matched ?? "n/a"}/${item.supporting_matched ?? "n/a"}/${item.context_matched ?? "n/a"} | context_score=${item.context_score ?? "n/a"} | event_contribution_score=${item.event_contribution_score ?? "n/a"} | top_rejected_reasons=${formatRejectedReasonsCompact(item.top_rejected_reasons)} | unresolved_source_summary=${formatUnresolvedSummaryCompact(item.unresolved_source_summary)}`
        );
      });
      items.forEach((item) => {
        lines.push(
          `${item.card_id} | version=${item.card_version || "n/a"} | formulas_count=${item.formulas_count ?? "n/a"} | priority_counts=${formatPriorityCounts(item.priority_counts)}`
        );
      });
      lines.push("working_time_ranges_difference");
      workingRangesDiff.forEach((item) => {
        lines.push(
          `${item.card_id}: ranges=${item.ranges_count ?? "n/a"} | primary=${item.primary_range?.start_local || "n/a"} -> ${item.primary_range?.end_local || "n/a"}`
        );
      });
      lines.push("best_candidate_difference");
      Object.entries(bestCandidateDiff).forEach(([cardId, item]) => {
        lines.push(
          `${cardId}: best_candidate=${item?.candidate_time_local || "n/a"} | score=${item?.score ?? "n/a"} | golden=${item?.golden_matched_count ?? "n/a"} | golden_orb_sum=${item?.golden_orb_sum ?? "n/a"}`
        );
      });
      lines.push("event_contribution_audit_difference");
      Object.entries(eventContributionDiff).forEach(([cardId, audit]) => {
        const list = Array.isArray(audit) ? audit : [];
        lines.push(`${cardId}: events=${list.length}`);
      });
      lines.push(`shared_rules: ${formatRuleListCompact(sharedRules)}`);
      lines.push(`v1_only_rules: ${formatRuleListCompact(v1OnlyRules)}`);
      lines.push(`v2_added_rules: ${formatRuleListCompact(v2AddedRules)}`);
      lines.push(`why_result_changed: ${compactSummary.why_result_changed || differences.why_result_changed || "n/a"}`);
      rpFormulaComparisonEl.textContent = lines.join("\n");
    }

    export function renderFormulaMultiCardReport(data) {
      const report = data?.formula_multi_card_report || null;
      rpFormulaMultiCardEl.textContent = "";
      if (!report || !report.enabled) {
        rpFormulaMultiCardEl.textContent = "formula_multi_card_report не запрошен.";
        return;
      }

      const cardAudit = Array.isArray(report.card_contribution_audit) ? report.card_contribution_audit : [];
      const eventTypeContribution = Array.isArray(report.event_type_contribution) ? report.event_type_contribution : [];
      const workingRanges = Array.isArray(report.overall_working_ranges) ? report.overall_working_ranges : [];
      const best = report.overall_best_candidate || {};
      const lines = [
        `formula_multi_card_report | selected_card_ids=${(report.selected_card_ids || []).join(", ") || "none"}`,
        `Overall best candidate | time=${best.candidate_time_local || "n/a"} | score=${best.score ?? "n/a"} | matched/rejected/missed=${best.matched_count ?? "n/a"}/${best.rejected_count ?? "n/a"}/${best.missed_count ?? "n/a"}`,
        `Overall working ranges: ${workingRanges.length}`,
      ];
      workingRanges.forEach((item, idx) => {
        lines.push(
          `#${idx + 1}: ${item.start_local || "n/a"} -> ${item.end_local || "n/a"} | best=${item.best_candidate || "n/a"} | golden=${item.golden_matched_count ?? "n/a"} | score=${item.score ?? "n/a"}`
        );
      });
      lines.push("Per-card contribution");
      cardAudit.forEach((item) => {
        lines.push(
          `${item.card_id || "n/a"} | matched/rejected/missed=${item.matched_count ?? "n/a"}/${item.rejected_count ?? "n/a"}/${item.missed_count ?? "n/a"} | golden/supporting/context=${item.golden_matched_count ?? "n/a"}/${item.supporting_matched_count ?? "n/a"}/${item.context_matched_count ?? "n/a"} | context_score=${item.context_score ?? "n/a"} | score=${item.score ?? "n/a"} | contribution=${item.contribution_to_final_candidate ?? "n/a"}`
        );
      });
      lines.push("event_type_contribution");
      eventTypeContribution.forEach((item) => {
        lines.push(
          `${formatEventTypeLabel(item.event_type)} | cards=${Array.isArray(item.card_ids) ? item.card_ids.join(", ") : "n/a"} | matched/rejected/missed=${item.matched_count ?? "n/a"}/${item.rejected_count ?? "n/a"}/${item.missed_count ?? "n/a"} | score=${item.score ?? "n/a"} | contribution=${item.contribution_to_final_candidate ?? "n/a"}`
        );
      });
      lines.push(`top_matched_rules: ${(report.top_matched_rules || []).join("; ") || "none"}`);
      lines.push(`top_rejected_reasons: ${formatRejectedReasonsCompact(report.top_rejected_reasons)}`);
      lines.push(`unresolved_source_summary: ${formatUnresolvedSummaryCompact(report.unresolved_source_summary)}`);
      rpFormulaMultiCardEl.textContent = lines.join("\n");
    }

    export function renderLegacyProConfirmations(data) {
      const methods = data.method_results || {};
      const methodStats = summarizeMethodStats(methods);
      const eventMap = buildProEventMap();
      const methodEntries = [];

      for (const [methodName, entries] of Object.entries(methods)) {
        const list = Array.isArray(entries) ? entries : [];
        if ((methodName === "lunars" || methodName === "totems")
            && isMethodInactive(methodStats, methodName)) {
          continue;
        }
        list.forEach((entry) => {
          methodEntries.push({
            methodName,
            eventId: entry?.event_id || "",
            eventScore: Number(entry?.event_score),
            matches: Array.isArray(entry?.matches) ? entry.matches : [],
            warnings: Array.isArray(entry?.warnings) ? entry.warnings : [],
          });
        });
      }

      rpMethodsSummaryEl.innerHTML = "";
      if (!methodEntries.length) {
        rpMethodsSummaryEl.textContent = "Нет данных по подтверждениям событий.";
        return;
      }

      methodEntries
        .sort((left, right) => Number((right.matches || []).length > 0) - Number((left.matches || []).length > 0))
        .forEach((item) => {
          const event = eventMap.get(item.eventId) || {};
          const matched = item.matches.length > 0;
          const eventTitle = event.title || `Событие ${item.eventId || "без id"}`;
          const eventType = formatEventTypeLabel(event.event_type);
          const eventDate = event.date_text || event.start_date || "дата не указана";
          const methodLabel = formatMethodLabel(item.methodName);
          const eventScore = Number.isFinite(item.eventScore) ? item.eventScore.toFixed(2) : "—";
          const warningsText = item.warnings.length ? item.warnings.join(", ") : "—";
          const matchedText = matched
            ? "Да. Технически подтверждено сигналом метода, требуется экспертная проверка."
            : "Нет, убедительного сигнала метода не получено.";

          const block = document.createElement("div");
          block.className = "interval-item";
          const titleNode = document.createElement("div");
          const titleStrong = document.createElement("strong");
          titleStrong.textContent = eventTitle;
          titleNode.appendChild(titleStrong);
          block.appendChild(titleNode);

          const lineTypeDate = document.createElement("div");
          lineTypeDate.textContent = `Тип: ${eventType} | Дата: ${eventDate}`;
          block.appendChild(lineTypeDate);

          const lineMethod = document.createElement("div");
          lineMethod.textContent = `Метод: ${methodLabel} | Подтверждено: ${matched ? "да" : "нет"}`;
          block.appendChild(lineMethod);

          if (!item.matches.length) {
            const lineAspect = document.createElement("div");
            lineAspect.textContent = "Аспекты: убедительных совпадений нет.";
            block.appendChild(lineAspect);
          } else {
            item.matches.forEach((match) => {
              const details = extractProMatchDetails(match);
              const lineAspect = document.createElement("div");
              lineAspect.textContent = `Аспект: ${details.aspect} | Орбис: ${details.orb} | Точки: ${details.points}`;
              block.appendChild(lineAspect);

              const lineScore = document.createElement("div");
              lineScore.textContent = `Score/weight: ${details.score} | Event score: ${eventScore}`;
              block.appendChild(lineScore);

              const lineExplanation = document.createElement("div");
              lineExplanation.textContent = `Пояснение: ${details.explanation}`;
              block.appendChild(lineExplanation);
            });
          }

          const lineStatus = document.createElement("div");
          lineStatus.textContent = `Статус: ${matchedText}`;
          block.appendChild(lineStatus);

          const lineWarnings = document.createElement("div");
          lineWarnings.className = "hint";
          lineWarnings.textContent = `Тех. предупреждения: ${warningsText}`;
          block.appendChild(lineWarnings);
          rpMethodsSummaryEl.appendChild(block);
        });
    }

    export function renderProConfirmations(data) {
      if (renderFormulaTestModeConfirmations(data)) {
        return;
      }
      renderLegacyProConfirmations(data);
    }

    export function renderProResult(data) {
      const best = Array.isArray(data.best_candidates) ? data.best_candidates : [];
      rpBestCandidatesEl.innerHTML = "";
      rpFormulaMultiCardEl.textContent = "";
      rpFormulaComparisonEl.textContent = "";
      const refinement = data.formula_refinement_results || null;
      const refinementBest = refinement && refinement.best_candidate ? refinement.best_candidate : null;
      const refinementCoarse = refinement && refinement.coarse_candidate ? refinement.coarse_candidate : null;
      const refinementRange = refinement && refinement.working_time_range ? refinement.working_time_range : null;
      const refinementRanges = refinement && Array.isArray(refinement.working_time_ranges) ? refinement.working_time_ranges : [];
      const refinementReference = refinement && refinement.reference_time ? refinement.reference_time : null;
      if (refinementBest) {
        const headline = document.createElement("div");
        headline.className = "pro-candidate pro-candidate-top";
        const bestTime = refinementBest.candidate_time_local || "n/a";
        const bestScoreNum = Number(refinementBest.score);
        const scorePct = Number.isFinite(bestScoreNum) ? Math.max(4, Math.min(100, Math.round(bestScoreNum))) : 0;
        const headlineWin = refinementRange
          ? `${refinementRange.start_local} → ${refinementRange.end_local}`
          : (refinementRanges[0] ? `${refinementRanges[0].start_local} → ${refinementRanges[0].end_local}` : "—");
        headline.innerHTML =
          `<div class="pc-head">` +
            `<span class="pc-rank">✦</span>` +
            `<span class="pc-time">${bestTime}</span>` +
            `<span class="pc-badge pc-badge-high">лучшее время</span>` +
          `</div>` +
          `<div class="pc-score">` +
            `<span class="pc-score-label">Совокупный балл</span>` +
            `<span class="pc-bar"><i style="width:${scorePct}%"></i></span>` +
            `<span class="pc-score-val">${Number.isFinite(bestScoreNum) ? bestScoreNum : "n/a"}</span>` +
          `</div>` +
          `<div class="hint">Рабочее окно времени рождения: ${headlineWin}</div>`;
        rpBestCandidatesEl.appendChild(headline);

        const refinementBlock = document.createElement("div");
        refinementBlock.className = "interval-item";
        const stepSeconds = Number.isFinite(Number(refinement.step_seconds)) ? Number(refinement.step_seconds) : null;
        const supportedSteps = Array.isArray(refinement.supported_step_seconds) ? refinement.supported_step_seconds : [];
        const bestFormulas = Array.isArray(refinementBest.best_formulas) ? refinementBest.best_formulas : [];
        const scoreBreakdown = refinementBest.score_breakdown || null;
        const rejectedReasons = formatRejectedReasonsCompact(refinementBest.top_rejected_reasons);
        const unresolvedSummary = formatUnresolvedSummaryCompact(refinementBest.unresolved_source_summary);
        const candidateConsistency = [
          `selected_candidate_time=${refinementBest.selected_candidate_time || "n/a"}`,
          `chart_build_time=${refinementBest.chart_build_time || "n/a"}`,
          `natal_houses_time=${refinementBest.natal_houses_time || "n/a"}`,
          `rulers_resolved_time=${refinementBest.rulers_resolved_time || "n/a"}`,
          `house_elements_resolved_time=${refinementBest.house_elements_resolved_time || "n/a"}`,
          `directed_points_time=${refinementBest.directed_points_time || "n/a"}`,
          `timezone_used=${refinementBest.timezone_used || refinement.timezone_used || "n/a"}`,
        ].join(" | ");
        const rangesMarkup = refinementRanges.length
          ? refinementRanges.map((item, idx) =>
              `<div>#${idx + 1}: ${item.start_local} → ${item.end_local} | best=${item.best_candidate || "n/a"} | golden=${item.golden_matched_count ?? "n/a"} | score=${item.score ?? "n/a"} | candidates=${item.candidate_count ?? "n/a"} | reason=${item.selection_reason || "n/a"}</div>`
            ).join("")
          : "<div>n/a</div>";
        refinementBlock.innerHTML =
          `<div><strong>Refinement inside Asc window</strong></div>` +
          `<div>Best candidate: ${refinementBest.candidate_time_local || "n/a"} | score=${refinementBest.score ?? "n/a"} | matched=${refinementBest.matched_count ?? "n/a"} | rejected=${refinementBest.rejected_count ?? "n/a"}</div>` +
          `<div>Step: ${stepSeconds != null ? `${stepSeconds}s` : "n/a"} | supported=${supportedSteps.length ? supportedSteps.join(", ") : "n/a"} | scanned=${refinement.scanned_candidates_count ?? "n/a"} | method=${refinement.direction_method || "n/a"}</div>` +
          `<div>Working range: ${refinementRange ? `${refinementRange.start_local} → ${refinementRange.end_local}` : "n/a"} | candidates=${refinementRange?.candidate_count ?? "n/a"} | criterion=${refinementRange?.criterion ?? "n/a"}</div>` +
          `<div>Working ranges: ${refinementRanges.length}</div>` +
          `${rangesMarkup}` +
          `<div>Coarse candidate: ${refinementCoarse?.candidate_time_local || "n/a"} | coarse score=${refinementCoarse?.score ?? "n/a"}</div>` +
          `<div>Reference candidate: ${refinementReference?.provided || "n/a"} | inside range=${refinementReference?.inside_working_time_range ?? "n/a"} | reference score=${refinementReference?.evaluation?.score ?? "n/a"}</div>` +
          `<div>Golden matched=${refinementBest.golden_matched_count ?? "n/a"} | golden orb sum=${refinementBest.golden_orb_sum ?? "n/a"} | supporting matched=${refinementBest.supporting_matched_count ?? "n/a"} | context matched=${refinementBest.context_matched_count ?? "n/a"} | context score=${refinementBest.context_score ?? "n/a"} | supporting bonus=${refinementBest.supporting_bonus ?? "n/a"}</div>` +
          `<div>Event confirmation score=${refinementBest.event_confirmation_score ?? "n/a"} | time refinement score=${refinementBest.time_refinement_score ?? "n/a"}</div>` +
          `<div><strong>Expert compact mode</strong>: top_rejected_reasons=${rejectedReasons} | unresolved_source_summary=${unresolvedSummary}</div>` +
          `<div>Candidate consistency: ${candidateConsistency}</div>` +
          `<div>Best formulas: ${bestFormulas.length ? bestFormulas.join("; ") : "n/a"}</div>` +
          `<div>Score breakdown: matched=${scoreBreakdown?.matched_formula_score ?? "n/a"} | orb=${scoreBreakdown?.orb_strength_score ?? "n/a"} | participation=${scoreBreakdown?.participant_bonus_score ?? "n/a"} | rejected_penalty=${scoreBreakdown?.rejected_penalty ?? "n/a"} | missed_penalty=${scoreBreakdown?.missing_penalty ?? "n/a"}</div>` +
          `<div>Golden breakdown: formula=${scoreBreakdown?.golden_formula_score ?? "n/a"} | golden orb quality=${scoreBreakdown?.golden_orb_quality_score ?? "n/a"} | supporting formula=${scoreBreakdown?.supporting_formula_score ?? "n/a"} | context formula=${scoreBreakdown?.context_formula_score ?? "n/a"} | supporting bonus=${scoreBreakdown?.supporting_bonus ?? "n/a"}</div>` +
          `<div>Selection reason: ${refinementBest.selection_reason || "n/a"}</div>` +
          `<div class="hint">Legacy coarse candidates remain below as debug/reference.</div>`;
        const contributionAudit = Array.isArray(refinementBest.event_contribution_audit) ? refinementBest.event_contribution_audit : [];
        if (contributionAudit.length) {
          const auditWrap = document.createElement("div");
          auditWrap.style.marginTop = "8px";
          auditWrap.innerHTML = renderTable(
            ["Вклад событий в результат", "Event type", "Date", "Score", "Contribution %", "Matched", "Rejected", "Missed", "Golden", "Supporting", "Context", "Context score"],
            contributionAudit.map((item) => [
              item.event_title || item.event_id || "—",
              item.event_type || "—",
              item.event_date || "—",
              item.score ?? "—",
              item.contribution_to_final_candidate ?? "—",
              item.matched_count ?? "—",
              item.rejected_count ?? "—",
              item.missed_count ?? "—",
              item.golden_matched_count ?? "—",
              item.supporting_matched_count ?? "—",
              item.context_matched_count ?? "—",
              item.context_score ?? "—",
            ])
          );
          refinementBlock.appendChild(auditWrap);
        }
        rpBestCandidatesEl.appendChild(refinementBlock);
      }
      if (!best.length) {
        if (!refinementBest) {
          rpBestCandidatesEl.innerHTML = "<div class='interval-item'>Кандидаты не найдены.</div>";
        }
      } else {
        const confClassMap = {
          very_low: "low", low: "low", low_medium: "mid", medium: "mid",
          medium_high: "high", high: "high", expert_high: "high",
        };
        const confLabelMap = {
          very_low: "очень низкая", low: "низкая", low_medium: "ниже средней",
          medium: "средняя", medium_high: "выше средней", high: "высокая", expert_high: "экспертная",
        };
        const totals = best.map((it) => Number(it.scores?.total)).filter(Number.isFinite);
        const maxTotal = totals.length ? Math.max(...totals) : 0;
        best.forEach((item, idx) => {
          const totalNum = Number(item.scores?.total);
          const totalText = Number.isFinite(totalNum) ? totalNum.toFixed(2) : "n/a";
          const pct = (Number.isFinite(totalNum) && maxTotal > 0)
            ? Math.max(4, Math.round((totalNum / maxTotal) * 100))
            : 0;
          const block = document.createElement("div");
          block.className = "pro-candidate" + (idx === 0 ? " pro-candidate-top" : "");
          block.style.setProperty("--i", String(idx));
          const preciseOnly = (data.confidence?.level === "high" || data.confidence?.level === "expert_high")
            ? ""
            : " · не считать точным временем";
          const source = item.source_asc_interval || {};
          const sourceStart = source.start_local_clipped || source.start_local || "—";
          const sourceEnd = source.end_local_clipped || source.end_local || "—";
          const sourceSign = source.sign_name_ru || source.sign_name_en || item.asc_sign || "—";
          const clippedNote = item.clipped_by_birth_date
            ? "Окно ограничено границами выбранной даты рождения."
            : "Окно полностью внутри выбранной даты рождения.";
          const confClass = confClassMap[item.confidence_level] || "mid";
          const confLabel = confLabelMap[item.confidence_level] || (item.confidence_level || "n/a");
          block.innerHTML =
            `<div class="pc-head">` +
              `<span class="pc-rank">#${idx + 1}</span>` +
              `<span class="pc-time">${item.candidate_time_local}</span>` +
              `<span class="pc-badge pc-badge-${confClass}">${confLabel}</span>` +
            `</div>` +
            `<div class="pc-score">` +
              `<span class="pc-score-label">Совокупный балл</span>` +
              `<span class="pc-bar"><i style="width:${pct}%"></i></span>` +
              `<span class="pc-score-val">${totalText}</span>` +
            `</div>` +
            `<div class="hint">Источник Asc: ${sourceSign} (${sourceStart} → ${sourceEnd})</div>` +
            `<div class="hint">${clippedNote}${preciseOnly}</div>`;
          rpBestCandidatesEl.appendChild(block);
        });
      }

      const confidence = data.confidence || {};
      const windowMinutes = Number.isFinite(Number(confidence.time_window_minutes))
        ? Number(confidence.time_window_minutes)
        : null;
      const windowExplanation = windowMinutes == null
        ? "Ширина окна: не определена."
        : `Ширина окна: ${windowMinutes} минут — это диапазон времени, внутри которого система ищет наиболее вероятное рождение. Это не точное время рождения.`;
      const confLevelPos = {
        very_low: 10, low: 24, low_medium: 38, medium: 52,
        medium_high: 68, high: 83, expert_high: 95,
      };
      const confLevelRu = {
        very_low: "очень низкая", low: "низкая", low_medium: "ниже средней", medium: "средняя",
        medium_high: "выше средней", high: "высокая", expert_high: "экспертная",
      };
      const confPos = confLevelPos[confidence.level] != null ? confLevelPos[confidence.level] : 50;
      const confRu = confLevelRu[confidence.level] || confidence.level || "не рассчитано";
      const confLevelStr = String(confidence.level || "");
      const ovClass = /high|expert/.test(confLevelStr) ? "high" : (/medium/.test(confLevelStr) ? "mid" : "low");
      rpConfidenceEl.innerHTML =
        `<div class="conf-top">` +
          `<span class="conf-cap">Уровень уверенности</span>` +
          `<span class="conf-level conf-${ovClass}">${confRu}</span>` +
        `</div>` +
        `<div class="confidence-meter">` +
          `<div class="cm-track"><span class="cm-marker" style="left:${confPos}%"></span></div>` +
          `<div class="cm-scale"><span>низкая</span><span>средняя</span><span>высокая</span></div>` +
        `</div>` +
        (windowMinutes != null
          ? `<div class="conf-window"><span class="cw-label">Окно поиска времени рождения</span><span class="cw-val">${windowMinutes} мин</span></div>`
          : "") +
        `<div class="hint" style="margin-top:10px;">${windowExplanation}</div>` +
        (confidence.explanation ? `<div class="hint">${confidence.explanation}</div>` : "");

      renderProConfirmations(data);
      renderFormulaMultiCardReport(data);
      renderFormulaCardComparison(data);

      const warnings = Array.isArray(data.warnings) ? data.warnings : [];
      const limitations = Array.isArray(data.limitations) ? data.limitations : [];
      rpWarningsEl.textContent =
        `warnings: ${warnings.join(", ") || "none"} | limitations: ${limitations.join(" | ") || "none"}`;
      if (rpExplainBodyEl) {
        rpExplainBodyEl.innerHTML = buildProExplainabilityHtml(data);
      }
    }

    export async function runUiProofPreviewFromQuery() {
      const params = new URLSearchParams(window.location.search);
      const previewMode = params.get("proof_preview");
      if (!previewMode) return;

      if (previewMode === "pro" || previewMode === "all" || previewMode === "comparison") {
        const proRes = await fetch("/api/preview/pro-result");
        if (!proRes.ok) {
          throw new Error("Не удалось загрузить preview Pro result");
        }
        const proData = await proRes.json();
        renderProResult(proData);
        if (previewMode === "comparison") {
          setTechnicalMode(true);
          setTab("rect-events");
          rpFormulaComparisonEl.scrollIntoView({ behavior: "auto", block: "center" });
          setRpStatus("Preview: V1 vs V2 comparison panel загружен из fixture.");
        } else {
          setRpStatus("Preview: финальный Pro panel загружен из fixture.");
        }
      }

      if (previewMode === "chart" || previewMode === "all") {
        const chartRes = await fetch("/api/preview/chart-result");
        if (!chartRes.ok) {
          throw new Error("Не удалось загрузить preview chart result");
        }
        const chartData = await chartRes.json();
        horoscopeBoxEl.textContent = chartData.horoscope_text || "Preview horoscope text.";
        renderExpertTables(chartData.chart_response, chartData.timezone || {}, chartData.warnings || []);
        expertWrapEl.classList.add("hidden");
        toggleExpertBtnEl.textContent = "Показать экспертную таблицу";
        modalEl.classList.add("active");
        setStatus("Preview: модальное окно обычной карты загружено из fixture.");
      }
    }

    export async function runProRectification() {
      if (rectEventsState.isBusy || rectDialogState.isBusy) {
        setRpStatus("Дождитесь завершения текущего шага.");
        setWzProStatus("Дождитесь завершения текущего шага.");
        return;
      }
      if (!rectificationWizardState.stage1.completed || !rectificationWizardState.stage2.completed) {
        const msg = "Сначала завершите диалог по Asc и сбор событий жизни.";
        setRpStatus(msg);
        setWzProStatus(msg);
        return;
      }
      const ascWindows = buildProAscWindowsFromStage1();
      if (!ascWindows.length) {
        setRpStatus("Сначала запустите Stage 1 (Asc-окна).");
        setWzProStatus("Сначала завершите Stage 1 и получите интервалы кандидатов.");
        return;
      }
      const events = buildProEventsFromStage2();
      if (!events.length) {
        setRpStatus("Сначала соберите события Stage 2 и завершите их.");
        setWzProStatus("Сначала завершите сбор событий Stage 2.");
        return;
      }

      const selectedFormulaCardId = rpFormulaCardIdEl.value || null;
      const selectedMultiCardIds = rpUseAllRelevantV2CardsEl.checked
        ? resolveRelevantV2DraftCardIds(events)
        : [];
      const payload = {
        birth_date_local: (sharedBirthContext.birthDateLocal || document.getElementById("rdBirthDate").value || "").split("T")[0],
        latitude: Number(sharedBirthContext.latitude ?? document.getElementById("rdLatitude").value),
        longitude: Number(sharedBirthContext.longitude ?? document.getElementById("rdLongitude").value),
        timezone_name: sharedBirthContext.timezoneName || timezoneNameEl.value || null,
        timezone_mode: sharedBirthContext.timezoneMode || timezoneModeEl.value || "auto",
        timezone_offset: (sharedBirthContext.timezoneMode || timezoneModeEl.value || "auto") === "manual"
          ? (sharedBirthContext.timezoneOffset || timezoneOffsetEl.value || "")
          : "",
        house_system: sharedBirthContext.houseSystem || document.getElementById("rdHouseSystem").value,
        zodiac_mode: sharedBirthContext.zodiacMode || rdZodiacModeEl.value,
        sidereal_mode: (sharedBirthContext.zodiacMode || rdZodiacModeEl.value) === "sidereal"
          ? (sharedBirthContext.siderealMode || rdSiderealModeEl.value || null)
          : null,
        asc_windows: ascWindows,
        events,
        settings: {
          candidate_step_minutes: 5,
          formula_card_id: selectedFormulaCardId,
          formula_card_ids: selectedMultiCardIds,
          compare_formula_card_ids: (!selectedMultiCardIds.length && rpCompareV1V2El.checked)
            ? resolveComparisonCardIds(selectedFormulaCardId)
            : [],
          include_directions: true,
          include_solars: true,
          include_lunars: false,
          include_transits: true,
          include_totems: false,
        },
      };
      appState.lastProRunPayload = JSON.parse(JSON.stringify(payload));

      const invalidReasons = [];
      if (!payload.birth_date_local || !/^\d{4}-\d{2}-\d{2}$/.test(payload.birth_date_local)) {
        invalidReasons.push("дата рождения");
      }
      if (!Number.isFinite(payload.latitude) || !Number.isFinite(payload.longitude)) {
        invalidReasons.push("координаты");
      }
      if (payload.timezone_mode === "manual" && !payload.timezone_offset) {
        invalidReasons.push("timezone_offset");
      }
      if (payload.timezone_mode !== "manual" && !payload.timezone_name && (!Number.isFinite(payload.latitude) || !Number.isFinite(payload.longitude))) {
        invalidReasons.push("timezone_name");
      }
      if (!Array.isArray(payload.events) || !payload.events.length) {
        invalidReasons.push("валидные события Stage 2");
      }
      if (rpUseAllRelevantV2CardsEl.checked && !selectedMultiCardIds.length) {
        invalidReasons.push("formula_card_ids");
      }
      if (invalidReasons.length) {
        const humanMsg = `Недостаточно данных для Pro-ректификации: ${invalidReasons.join(", ")}.`;
        setRpStatus(humanMsg);
        setWzProStatus(humanMsg);
        return;
      }

      const heavyProWarning = getHeavyProRunWarning(payload);
      if (selectedMultiCardIds.length) {
        rpCompareV1V2El.checked = false;
      }
      setRpStatus(heavyProWarning || "Запускаем Pro-ректификацию...");
      setWzProStatus(heavyProWarning || "Запускаем Pro-ректификацию...");
      showLlmOverlay(heavyProWarning ? `${heavyProWarning} Запускаем Pro-ректификацию...` : "Запуск Pro-ректификации...");
      try {
        const res = await fetchWithTimeout("/api/rectification/pro/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_base_url: document.getElementById("reApiBaseUrl").value.trim(),
            payload,
          }),
        }, 620000);
        const { jsonPayload, errorText } = await parseResponseBody(res);
        if (!res.ok) {
          throw new Error(errorText);
        }
        if (!jsonPayload) {
          throw new Error("Пустой ответ API");
        }
        renderProResult(jsonPayload);
        setRpStatus(`Готово. confidence=${jsonPayload.confidence?.level || "n/a"}`);
        rectificationWizardState.pro.started = true;
        rectificationWizardState.pro.completed = true;
        rectificationWizardState.pro.result = jsonPayload;
        setWzProStatus(`Готово. confidence=${jsonPayload.confidence?.level || "n/a"}`);
        renderWizardProgress();
      } catch (err) {
        setRpStatus("Ошибка: " + (err?.message || "network error"));
        setWzProStatus("Ошибка: " + (err?.message || "network error"));
      } finally {
        hideLlmOverlay();
      }
    }
