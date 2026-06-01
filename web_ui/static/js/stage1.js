// Авто-извлечено из main.js (build-split). Модуль: stage1.
import { rdCurrentQuestionWrapEl, rdFinalResultEl, rdHistoryEl, rdLastLlmJsonBoxEl, rdNoQuestionTextEl, rdOptionsWrapEl, rdProbabilityTextEl, rdPromptTextEl, rdQuestionTextEl, rdRectJsonBoxEl, rdSiderealModeEl, rdTesterThanksEl, rdUsageSummaryBoxEl, rdZodiacModeEl } from "./dom.js";
import { rectDialogState } from "./state.js";
import { extractErrorText, formatCandidateGroupText, formatIntervalLine, formatStage1SecondaryCandidatesHtml, formatUsage, formatWarnings } from "./format.js";
import { getRectDialogContextPatch, syncSharedBirthContext } from "./state-sync.js";
import { hideLlmOverlay, setRdStatus, showLlmOverlay } from "./ui.js";
import { updateWizardContextFromCurrentStates } from "./wizard.js";

    export function addUsageToTotals(usage) {
      if (!usage) return;
      const keys = ["input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_tokens"];
      keys.forEach((key) => {
        const value = usage[key];
        if (typeof value === "number" && Number.isFinite(value)) {
          rectDialogState.usageTotal[key] += value;
        }
      });
      rectDialogState.usageSteps.push(formatUsage(usage));
    }

    export function renderUsageSummary() {
      rdUsageSummaryBoxEl.textContent = JSON.stringify(
        {
          total: rectDialogState.usageTotal,
          steps: rectDialogState.usageSteps,
        },
        null,
        2
      );
    }

    export function resetRectDialogState() {
      rectDialogState.rectificationDocument = null;
      rectDialogState.dialogHistory = [];
      rectDialogState.stepCount = 0;
      rectDialogState.currentQuestion = null;
      rectDialogState.selectedOption = null;
      rectDialogState.lastLlmRaw = null;
      rectDialogState.isBusy = false;
      rectDialogState.usageSteps = [];
      rectDialogState.usageTotal = {
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
        cached_input_tokens: 0,
        reasoning_tokens: 0,
      };

      rdHistoryEl.innerHTML = "";
      rdFinalResultEl.textContent = "Финальный результат пока не получен.";
      rdTesterThanksEl.classList.add("hidden");
      rdRectJsonBoxEl.textContent = "";
      rdLastLlmJsonBoxEl.textContent = "";
      rdProbabilityTextEl.textContent = "";
      rdQuestionTextEl.textContent = "";
      rdOptionsWrapEl.innerHTML = "";
      rdCurrentQuestionWrapEl.classList.add("hidden");
      rdNoQuestionTextEl.classList.remove("hidden");
      renderUsageSummary();
    }

    export function appendAssistantMessage(llmJson, usage) {
      const entry = {
        role: "assistant",
        ...llmJson,
        usage: formatUsage(usage),
      };
      rectDialogState.dialogHistory.push(entry);

      if (llmJson.type === "ask_question") {
        rectDialogState.currentQuestion = llmJson;
        rectDialogState.selectedOption = null;
      } else {
        rectDialogState.currentQuestion = null;
      }
    }

    export function renderDialogHistory() {
      rdHistoryEl.innerHTML = "";
      if (!rectDialogState.dialogHistory.length) {
        rdHistoryEl.innerHTML = "<div class='hint'>История пока пуста.</div>";
        return;
      }

      let uiStep = 1;
      for (let i = 0; i < rectDialogState.dialogHistory.length; i++) {
        const item = rectDialogState.dialogHistory[i];
        if (item.role !== "assistant") {
          continue;
        }

        if (item.type === "ask_question") {
          const userItem = rectDialogState.dialogHistory[i + 1]?.role === "user"
            ? rectDialogState.dialogHistory[i + 1]
            : null;

          const qMsg = document.createElement("div");
          qMsg.className = "msg assistant";
          qMsg.innerHTML =
            `<div class="msg-head">Шаг ${uiStep} · вопрос</div>` +
            `<div>${item.question_text || "-"}</div>` +
            (item.debug_probability_text ? `<div class="usage-mini">${item.debug_probability_text}</div>` : "");
          rdHistoryEl.appendChild(qMsg);

          if (userItem) {
            const aMsg = document.createElement("div");
            aMsg.className = "msg user";
            aMsg.innerHTML =
              `<div class="msg-head">Ваш ответ</div>` +
              `<div>${userItem.selected_option_text || "—"}</div>`;
            rdHistoryEl.appendChild(aMsg);
            i += 1;
          }
          uiStep += 1;
          continue;
        }

        if (item.type === "final_result") {
          const p = item.primary_candidate || {};
          const ranges = Array.isArray(p.time_ranges_local) && p.time_ranges_local.length
            ? p.time_ranges_local
            : (p.time_range_local ? [p.time_range_local] : []);
          const rangesHtml = ranges.length
            ? `<div>Интервалы:<br/>${ranges.map((r, idx) => `${idx + 1}) ${formatIntervalLine(r.start, r.end)}`).join("<br/>")}</div>`
            : "<div>Интервалы: не указаны</div>";
          const candidateGroupText = formatCandidateGroupText(item.candidate_group);
          const secondaryHtml = formatStage1SecondaryCandidatesHtml(item.secondary_candidates);
          const msg = document.createElement("div");
          msg.className = "msg assistant";
          msg.innerHTML =
            `<div class="msg-head">Финальный шаг</div>` +
            `<div><strong>Итог:</strong> ${p.sign_name_ru || ""} (${p.sign_name_en || ""})</div>` +
            rangesHtml +
            `<div>Вероятность: ${p.probability ?? "n/a"}</div>` +
            `<div style="margin-top:6px;"><strong>Почему выбран кандидат:</strong> ${item.explanation_text || item.summary_text || ""}</div>` +
            `<div style="margin-top:6px;"><strong>Вторичные кандидаты:</strong><br/>${secondaryHtml}</div>` +
            (candidateGroupText ? `<div class="usage-mini">${candidateGroupText}</div>` : "");
          rdHistoryEl.appendChild(msg);
        }
      }
    }

    export function renderCurrentQuestion() {
      const q = rectDialogState.currentQuestion;
      if (!q || q.type !== "ask_question") {
        rdCurrentQuestionWrapEl.classList.add("hidden");
        rdNoQuestionTextEl.classList.remove("hidden");
        return;
      }

      rdCurrentQuestionWrapEl.classList.remove("hidden");
      rdNoQuestionTextEl.classList.add("hidden");
      rdProbabilityTextEl.textContent = q.debug_probability_text || "";
      rdQuestionTextEl.textContent = q.question_text || "";
      rdOptionsWrapEl.innerHTML = "";

      (q.options || []).forEach((option) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn option";
        if (rectDialogState.selectedOption?.id === option.id) {
          btn.classList.add("active");
        }
        btn.disabled = rectDialogState.isBusy;
        btn.textContent = `${option.id}. ${option.text}`;
        btn.addEventListener("click", async () => {
          if (rectDialogState.isBusy) return;
          rectDialogState.selectedOption = { id: option.id, text: option.text };
          renderCurrentQuestion();
          await continueRectificationDialogWithOption(rectDialogState.selectedOption);
        });
        rdOptionsWrapEl.appendChild(btn);
      });
    }

    export function renderFinalResult() {
      const lastAssistant = [...rectDialogState.dialogHistory]
        .reverse()
        .find((x) => x.role === "assistant" && x.type === "final_result");

      if (!lastAssistant) {
        rdFinalResultEl.textContent = "Финальный результат пока не получен.";
        rdTesterThanksEl.classList.add("hidden");
        return;
      }

      const primary = lastAssistant.primary_candidate || {};
      const primaryRanges = Array.isArray(primary.time_ranges_local) && primary.time_ranges_local.length
        ? primary.time_ranges_local
        : (primary.time_range_local ? [primary.time_range_local] : []);
      const primaryRangesHtml = primaryRanges.length
        ? primaryRanges
            .map((item, idx) => `<div>${idx + 1}) ${formatIntervalLine(item.start, item.end)}</div>`)
            .join("")
        : "<div>Интервалы не определены.</div>";
      const secondaryHtml = formatStage1SecondaryCandidatesHtml(lastAssistant.secondary_candidates || []);
      const candidateGroupText = formatCandidateGroupText(lastAssistant.candidate_group);
      const elementLabelMap = { fire: "Огонь", earth: "Земля", air: "Воздух", water: "Вода" };
      const modalityLabelMap = { cardinal: "кардинальный", fixed: "фиксированный", mutable: "мутабельный" };
      const leadingElement = lastAssistant.leading_element
        ? (elementLabelMap[lastAssistant.leading_element] || lastAssistant.leading_element)
        : "не определена";
      const leadingModality = lastAssistant.leading_modality
        ? (modalityLabelMap[lastAssistant.leading_modality] || lastAssistant.leading_modality)
        : "не определён";
      const methodLimitations = Array.isArray(lastAssistant.method_limitations)
        ? lastAssistant.method_limitations
        : [];
      const limitationsHtml = methodLimitations.length
        ? `<div style="margin-top:8px;"><strong>Ограничения метода:</strong><br/>${methodLimitations.map((x) => `• ${x}`).join("<br/>")}</div>`
        : "";
      const warnings = Array.isArray(lastAssistant.warnings) ? lastAssistant.warnings : [];
      const warningsHtml = warnings.length
        ? `<div style="margin-top:6px;"><strong>Предупреждения:</strong>${formatWarnings(warnings)}</div>`
        : "";
      rdFinalResultEl.innerHTML =
        `<div><strong>Стихия:</strong> ${leadingElement}</div>` +
        `<div><strong>Крест:</strong> ${leadingModality}</div>` +
        `<div><strong>Основной кандидат:</strong> ${primary.sign_name_ru || ""} (${primary.sign_name_en || ""})</div>` +
        `<div style="margin-top:6px;"><strong>Интервалы:</strong>${primaryRangesHtml}</div>` +
        `<div><strong>Вероятность:</strong> ${primary.probability ?? "n/a"}</div>` +
        `<div style="margin-top:6px;"><strong>Почему выбран кандидат:</strong> ${lastAssistant.explanation_text || lastAssistant.summary_text || ""}</div>` +
        `<div style="margin-top:6px;"><strong>Вторичные кандидаты:</strong><br/>${secondaryHtml}</div>` +
        (candidateGroupText ? `<div style="margin-top:6px;"><strong>Группа кандидатов:</strong> ${candidateGroupText}</div>` : "") +
        warningsHtml +
        `<div style="margin-top:8px;">${lastAssistant.summary_text || ""}</div>` +
        limitationsHtml;
      rdTesterThanksEl.classList.remove("hidden");
    }

    export function renderRectDialogAll() {
      rdRectJsonBoxEl.textContent = rectDialogState.rectificationDocument
        ? JSON.stringify(rectDialogState.rectificationDocument, null, 2)
        : "";
      rdLastLlmJsonBoxEl.textContent = rectDialogState.lastLlmRaw
        ? JSON.stringify(rectDialogState.lastLlmRaw, null, 2)
        : "";
      renderDialogHistory();
      renderCurrentQuestion();
      renderFinalResult();
      renderUsageSummary();
    }

    export async function startRectificationDialog() {
      syncSharedBirthContext(getRectDialogContextPatch(), { silent: false });
      if (rectDialogState.isBusy) {
        return;
      }
      rectDialogState.isBusy = true;
      setRdStatus("Запуск ректификации...");
      showLlmOverlay("Запрос в нейросеть отправлен, ждите...");
      const zodiacMode = rdZodiacModeEl.value;
      const sidMode = rdSiderealModeEl.value || null;
      const body = {
        api_base_url: document.getElementById("rdApiBaseUrl").value.trim(),
        birth_date_local: document.getElementById("rdBirthDate").value,
        latitude: Number(document.getElementById("rdLatitude").value),
        longitude: Number(document.getElementById("rdLongitude").value),
        house_system: document.getElementById("rdHouseSystem").value,
        zodiac_mode: zodiacMode,
        sidereal_mode: zodiacMode === "sidereal" ? sidMode : null,
        prompt_text: rdPromptTextEl.value,
        user_profile_note: document.getElementById("rdUserProfileNote").value.trim() || null,
      };

      try {
        const res = await fetch("/api/rectification/dialog/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          setRdStatus("Ошибка: " + extractErrorText(data));
          return;
        }

        resetRectDialogState();
        rectDialogState.rectificationDocument = data.rectification_document;
        rectDialogState.lastLlmRaw = data.openai_raw_response || data.llm_json;
        rectDialogState.stepCount = data.step_count || 0;
        addUsageToTotals(data.usage);
        appendAssistantMessage(data.llm_json, data.usage);
        renderRectDialogAll();
        updateWizardContextFromCurrentStates();

        setRdStatus(
          (data.llm_json?.type === "final_result" ? "Получен финальный результат." : "Ректификация запущена.") +
          formatWarnings(data.warnings)
        );
      } catch (err) {
        setRdStatus("Ошибка: " + (err?.message || "network error"));
      } finally {
        rectDialogState.isBusy = false;
        hideLlmOverlay();
      }
    }

    export async function continueRectificationDialogWithOption(selectedOption) {
      if (!rectDialogState.rectificationDocument) {
        setRdStatus("Сначала нажмите 'Начать ректификацию'.");
        return;
      }
      if (!rectDialogState.currentQuestion || rectDialogState.currentQuestion.type !== "ask_question") {
        setRdStatus("Сейчас нет активного вопроса.");
        return;
      }
      if (!selectedOption) {
        setRdStatus("Выберите вариант ответа.");
        return;
      }
      if (rectDialogState.isBusy) {
        return;
      }

      rectDialogState.isBusy = true;
      renderCurrentQuestion();

      const userResponse = {
        selected_option_id: selectedOption.id,
        selected_option_text: selectedOption.text,
        free_text: null,
      };
      const body = {
        prompt_text: rdPromptTextEl.value,
        rectification_document: rectDialogState.rectificationDocument,
        dialog_history: rectDialogState.dialogHistory,
        step_count: rectDialogState.stepCount,
        mode: "next_question",
        user_profile_note: document.getElementById("rdUserProfileNote").value.trim() || null,
        user_response: userResponse,
      };

      setRdStatus("Переходим к следующему вопросу...");
      showLlmOverlay("Запрос в нейросеть отправлен, ждите...");
      try {
        const res = await fetch("/api/rectification/dialog/continue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          setRdStatus("Ошибка: " + extractErrorText(data));
          return;
        }

        rectDialogState.dialogHistory.push({
          role: "user",
          selected_option_id: userResponse.selected_option_id,
          selected_option_text: userResponse.selected_option_text,
          free_text: null,
        });

        rectDialogState.lastLlmRaw = data.openai_raw_response || data.llm_json;
        rectDialogState.stepCount = data.step_count || rectDialogState.stepCount;
        addUsageToTotals(data.usage);
        appendAssistantMessage(data.llm_json, data.usage);
        renderRectDialogAll();
        updateWizardContextFromCurrentStates();

        setRdStatus(
          (data.llm_json?.type === "final_result" ? "Получен финальный результат." : "Новый вопрос получен.") +
          formatWarnings(data.warnings)
        );
      } catch (err) {
        setRdStatus("Ошибка: " + (err?.message || "network error"));
      } finally {
        rectDialogState.isBusy = false;
        hideLlmOverlay();
        renderCurrentQuestion();
      }
    }
