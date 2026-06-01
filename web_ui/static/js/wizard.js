// Авто-извлечено из main.js (build-split). Модуль: wizard.
import { rectIntervalsListEl, rectJsonBoxEl, rpBestCandidatesEl, rpConfidenceEl, rpExplainBodyEl, rpFormulaComparisonEl, rpMethodsSummaryEl, rpRawBoxEl, rpWarningsEl, wzBirthDateEl, wzCityQueryEl, wzIntervalsListEl, wzProgressTextEl, wzStage1SummaryEl, wzStage2ContextEl, wzStepBadgeEls, wzStepHintEls, wzTimezoneModeEl, wzTimezoneNameEl, wzTimezoneOffsetEl } from "./dom.js";
import { appState, rectDialogState, rectEventsState, rectificationWizardState } from "./state.js";
import { formatCandidateGroupText, formatIntervalLine, formatStage1SecondaryCandidatesHtml, formatWarnings } from "./format.js";
import { runRectification } from "./chart.js";
import { buildCoordinateContextPatch } from "./coords.js";
import { getWizardContextPatch, syncSharedBirthContext } from "./state-sync.js";
import { setWzProStatus, setWzStatus } from "./ui.js";

    export function applyWizardBirthDataFromUi() {
      const coords = buildCoordinateContextPatch("wizard");
      rectificationWizardState.birthDateLocal = wzBirthDateEl.value || null;
      rectificationWizardState.birthPlace = wzCityQueryEl.value.trim() || null;
      rectificationWizardState.latitude = coords.latitude;
      rectificationWizardState.longitude = coords.longitude;
      rectificationWizardState.timezoneMode = wzTimezoneModeEl.value;
      rectificationWizardState.timezoneName = wzTimezoneNameEl.value || null;
      rectificationWizardState.timezoneOffset = wzTimezoneOffsetEl.value || null;
    }

    export function resetWizardDerivedState() {
      rectificationWizardState.ascIntervals = null;
      rectificationWizardState.stage1 = {
        started: false,
        completed: false,
        primaryCandidate: null,
        secondaryCandidates: [],
        timeRangesLocal: [],
        elementScores: null,
        modalityScores: null,
        signScores: null,
        candidateGroup: null,
        leadingElement: null,
        leadingModality: null,
        summaryText: null,
        explanationText: null,
        methodLimitations: [],
        stageWarnings: [],
      };
      rectificationWizardState.stage2 = {
        started: false,
        completed: false,
        events: [],
        eventCards: [],
      };
      rectificationWizardState.pro = {
        started: false,
        completed: false,
        result: null,
      };
      wzIntervalsListEl.innerHTML = "<div class='interval-item'>Сначала рассчитайте интервалы на шаге 1.</div>";
      wzStage1SummaryEl.textContent = "Stage 1 ещё не завершён.";
      rpBestCandidatesEl.innerHTML = "";
      rpConfidenceEl.textContent = "Pro-ректификация ещё не запускалась.";
      rpMethodsSummaryEl.textContent = "";
      rpWarningsEl.textContent = "";
      rpFormulaComparisonEl.textContent = "";
      if (rpExplainBodyEl) {
        rpExplainBodyEl.textContent = "";
      }
      rpRawBoxEl.textContent = "";
      appState.lastProRunPayload = null;
      setWzProStatus("");
    }

    export function resetWizardScenario() {
      resetWizardDerivedState();
      updateWizardContextFromCurrentStates();
      renderWizardProgress();
      setWzStatus("Мастер-сценарий сброшен.");
    }

    export function getWizardCurrentStep() {
      if (!Array.isArray(rectificationWizardState.ascIntervals) || !rectificationWizardState.ascIntervals.length) return 1;
      if (!rectificationWizardState.stage1.completed) return 3;
      if (!rectificationWizardState.stage2.completed) return 4;
      if (!rectificationWizardState.pro.completed) return 5;
      return 5;
    }

    export function renderWizardProgress() {
      const activeStep = getWizardCurrentStep();
      const doneMap = [
        !!(Array.isArray(rectificationWizardState.ascIntervals) && rectificationWizardState.ascIntervals.length),
        !!(Array.isArray(rectificationWizardState.ascIntervals) && rectificationWizardState.ascIntervals.length),
        !!rectificationWizardState.stage1.completed,
        !!rectificationWizardState.stage2.completed,
        !!rectificationWizardState.pro.completed,
      ];
      wzStepBadgeEls.forEach((el, idx) => {
        if (!el) return;
        const step = idx + 1;
        el.classList.toggle("active", step === activeStep);
        el.classList.toggle("done", doneMap[idx] && step < activeStep + 1);
      });

      wzStepHintEls[0].textContent = doneMap[0] ? "готово" : "заполните дату и место";
      wzStepHintEls[1].textContent = doneMap[1] ? `${(rectificationWizardState.ascIntervals || []).length} интервалов` : "ожидает расчёт";
      wzStepHintEls[2].textContent = doneMap[2] ? "завершён" : "нужен финал Stage 1";
      wzStepHintEls[3].textContent = doneMap[3] ? `${rectificationWizardState.stage2.events.length} событий` : "нужен финал Stage 2";
      wzStepHintEls[4].textContent = doneMap[4] ? "готово" : "ожидает запуск";
      wzProgressTextEl.textContent = `Шаг ${activeStep} из 5`;
    }

    export function renderWizardStage1Summary() {
      if (!rectificationWizardState.stage1.completed || !rectificationWizardState.stage1.primaryCandidate) {
        wzStage1SummaryEl.textContent = "Stage 1 ещё не завершён.";
        return;
      }
      const elementLabelMap = { fire: "Огонь", earth: "Земля", air: "Воздух", water: "Вода" };
      const modalityLabelMap = { cardinal: "кардинальный", fixed: "фиксированный", mutable: "мутабельный" };
      const p = rectificationWizardState.stage1.primaryCandidate || {};
      const ranges = Array.isArray(p.time_ranges_local) && p.time_ranges_local.length
        ? p.time_ranges_local
        : rectificationWizardState.stage1.timeRangesLocal;
      const rangesHtml = ranges.length
        ? ranges.map((r, i) => `<div>${i + 1}) ${formatIntervalLine(r.start, r.end)}</div>`).join("")
        : "<div>Интервалы не определены.</div>";
      const secondaryHtml = formatStage1SecondaryCandidatesHtml(rectificationWizardState.stage1.secondaryCandidates || []);
      const candidateGroupText = formatCandidateGroupText(rectificationWizardState.stage1.candidateGroup);
      const leadingElement = rectificationWizardState.stage1.leadingElement
        ? (elementLabelMap[rectificationWizardState.stage1.leadingElement] || rectificationWizardState.stage1.leadingElement)
        : "не определена";
      const leadingModality = rectificationWizardState.stage1.leadingModality
        ? (modalityLabelMap[rectificationWizardState.stage1.leadingModality] || rectificationWizardState.stage1.leadingModality)
        : "не определён";
      const limitations = Array.isArray(rectificationWizardState.stage1.methodLimitations)
        ? rectificationWizardState.stage1.methodLimitations
        : [];
      const limitationsHtml = limitations.length
        ? `<div style="margin-top:6px;"><strong>Ограничения метода:</strong><br/>${limitations.map((x) => `• ${x}`).join("<br/>")}</div>`
        : "";
      const stageWarnings = Array.isArray(rectificationWizardState.stage1.stageWarnings)
        ? rectificationWizardState.stage1.stageWarnings
        : [];
      const warningsHtml = stageWarnings.length
        ? `<div style="margin-top:6px;"><strong>Предупреждения:</strong>${formatWarnings(stageWarnings)}</div>`
        : "";
      wzStage1SummaryEl.innerHTML =
        `<div><strong>Стихия:</strong> ${leadingElement}</div>` +
        `<div><strong>Крест:</strong> ${leadingModality}</div>` +
        `<div><strong>Основной кандидат:</strong> ${p.sign_name_ru || ""} (${p.sign_name_en || ""})</div>` +
        `<div style="margin-top:6px;"><strong>Вероятность:</strong> ${p.probability ?? "n/a"}</div>` +
        `<div style="margin-top:6px;"><strong>Интервалы:</strong>${rangesHtml}</div>` +
        `<div style="margin-top:6px;"><strong>Почему выбран кандидат:</strong> ${rectificationWizardState.stage1.explanationText || rectificationWizardState.stage1.summaryText || "—"}</div>` +
        (candidateGroupText ? `<div style="margin-top:6px;"><strong>Группа кандидатов:</strong> ${candidateGroupText}</div>` : "") +
        `<div style="margin-top:6px;"><strong>Вторичные кандидаты:</strong><br/>${secondaryHtml}</div>` +
        warningsHtml +
        limitationsHtml;
    }

    export function renderWizardStage2Context() {
      const p = rectificationWizardState.stage1.primaryCandidate || {};
      const ranges = Array.isArray(p.time_ranges_local) && p.time_ranges_local.length
        ? p.time_ranges_local
        : rectificationWizardState.stage1.timeRangesLocal;
      const rangeText = ranges.length
        ? ranges.map((r, i) => `${i + 1}) ${formatIntervalLine(r.start, r.end)}`).join("<br/>")
        : "не определены";
      const eventsCount = rectificationWizardState.stage2.events.length;
      wzStage2ContextEl.innerHTML =
        `<div><strong>Контекст ректификации:</strong></div>` +
        `<div>Дата рождения: ${rectificationWizardState.birthDateLocal || "—"}</div>` +
        `<div>Место рождения: ${rectificationWizardState.birthPlace || "—"}</div>` +
        `<div>Основной Asc-кандидат: ${p.sign_name_ru || p.sign_name_en || "—"}</div>` +
        `<div>Интервалы:<br/>${rangeText}</div>` +
        `<div>Собрано событий: ${eventsCount} / желательно 5–7</div>`;
    }

    export function updateWizardContextFromCurrentStates() {
      const lastFinal = [...rectDialogState.dialogHistory]
        .reverse()
        .find((x) => x.role === "assistant" && x.type === "final_result");
      if (lastFinal) {
        rectificationWizardState.stage1.started = true;
        rectificationWizardState.stage1.completed = true;
        rectificationWizardState.stage1.primaryCandidate = lastFinal.primary_candidate || null;
        rectificationWizardState.stage1.secondaryCandidates = Array.isArray(lastFinal.secondary_candidates)
          ? lastFinal.secondary_candidates
          : [];
        const ranges = Array.isArray(lastFinal.primary_candidate?.time_ranges_local) && lastFinal.primary_candidate.time_ranges_local.length
          ? lastFinal.primary_candidate.time_ranges_local
          : (lastFinal.primary_candidate?.time_range_local ? [lastFinal.primary_candidate.time_range_local] : []);
        rectificationWizardState.stage1.timeRangesLocal = ranges;
        rectificationWizardState.stage1.elementScores = lastFinal.element_scores || null;
        rectificationWizardState.stage1.modalityScores = lastFinal.modality_scores || null;
        rectificationWizardState.stage1.signScores = lastFinal.sign_scores || null;
        rectificationWizardState.stage1.candidateGroup = lastFinal.candidate_group || null;
        rectificationWizardState.stage1.leadingElement = lastFinal.leading_element || null;
        rectificationWizardState.stage1.leadingModality = lastFinal.leading_modality || null;
        rectificationWizardState.stage1.methodLimitations = Array.isArray(lastFinal.method_limitations)
          ? lastFinal.method_limitations
          : [];
        rectificationWizardState.stage1.summaryText = lastFinal.summary_text || null;
        rectificationWizardState.stage1.explanationText = lastFinal.explanation_text || null;
        rectificationWizardState.stage1.stageWarnings = Array.isArray(lastFinal.warnings)
          ? lastFinal.warnings
          : [];
      }

      if (rectEventsState.finalized && Array.isArray(rectEventsState.finalized.events)) {
        rectificationWizardState.stage2.started = true;
        rectificationWizardState.stage2.completed = true;
        rectificationWizardState.stage2.events = rectEventsState.finalized.events;
        rectificationWizardState.stage2.eventCards = rectEventsState.finalized.events;
      }
      renderWizardStage1Summary();
      renderWizardStage2Context();
      renderWizardProgress();
    }

    export function syncWizardToModuleFields() {
      syncSharedBirthContext(getWizardContextPatch(), { silent: true });
    }

    export async function runWizardStep1() {
      syncSharedBirthContext(getWizardContextPatch(), { silent: false });
      applyWizardBirthDataFromUi();
      await runRectification();
      try {
        const parsed = rectJsonBoxEl.textContent ? JSON.parse(rectJsonBoxEl.textContent) : null;
        rectificationWizardState.ascIntervals = parsed?.asc_sign_intervals || [];
      } catch {
        rectificationWizardState.ascIntervals = [];
      }
      wzIntervalsListEl.innerHTML = rectIntervalsListEl.innerHTML || "<div class='interval-item'>Интервалы не найдены.</div>";
      renderWizardProgress();
      setWzStatus(`Asc-интервалы рассчитаны: ${(rectificationWizardState.ascIntervals || []).length}`);
    }
