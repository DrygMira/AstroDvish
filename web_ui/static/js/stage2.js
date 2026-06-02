// Авто-извлечено из main.js (build-split). Модуль: stage2.
import { reEventsListEl, reNoQuestionTextEl, reQuestionMetaEl, reQuestionTextEl, reQuestionWrapEl, reRepeatCountEl, reSummaryEl, reWarningsEl } from "./dom.js";
import { rectEventsState } from "./state.js";
import { parseResponseBody } from "./api.js";
import { hideLlmOverlay, setReStatus, showLlmOverlay } from "./ui.js";
import { resetWizardDerivedState, updateWizardContextFromCurrentStates } from "./wizard.js";

    export function resetRectEventsInputs() {
      document.getElementById("reTitle").value = "";
      document.getElementById("reDateText").value = "";
      document.getElementById("reImpactLevel").value = "";
      document.getElementById("reRepeatCount").value = "1";
      document.getElementById("reSequenceNumber").value = "";
      document.getElementById("reNotes").value = "";
    }

    export function countCollectedEventsForQuestion(questionId) {
      if (!Array.isArray(rectEventsState.dialogHistory)) return 0;
      return rectEventsState.dialogHistory.filter((item) => {
        if (!item || item.role !== "user") return false;
        if (item.question_id !== questionId) return false;
        const event = item.event;
        return event && !event.user_skipped;
      }).length;
    }

    export function getRepeatTargetFromHistory(questionId) {
      if (!Array.isArray(rectEventsState.dialogHistory)) return null;
      const values = rectEventsState.dialogHistory
        .filter((item) => item && item.role === "user" && item.question_id === questionId)
        .map((item) => Number(item?.raw_answer?.repeat_count))
        .filter((value) => Number.isFinite(value) && value >= 1);
      if (!values.length) return null;
      return Math.max(...values);
    }

    export function resetRectEventsState() {
      rectEventsState.dialogHistory = [];
      rectEventsState.currentQuestion = null;
      rectEventsState.finalized = null;
      rectEventsState.rawLastResponse = null;
      rectEventsState.isBusy = false;
      reSummaryEl.textContent = "Сбор событий ещё не завершён.";
      reEventsListEl.innerHTML = "";
      reWarningsEl.textContent = "";
      reQuestionWrapEl.classList.add("hidden");
      reNoQuestionTextEl.classList.remove("hidden");
      reQuestionMetaEl.textContent = "";
      reQuestionTextEl.textContent = "";
      resetRectEventsInputs();
      resetWizardDerivedState();
    }

    export function renderRectEventsQuestion() {
      const question = rectEventsState.currentQuestion;
      const disabled = rectEventsState.isBusy;
      document.getElementById("reAnswerBtn").disabled = disabled;
      document.getElementById("reSkipBtn").disabled = disabled;
      document.getElementById("reFinalizeBtn").disabled = disabled;
      document.getElementById("reStartBtn").disabled = disabled;
      document.getElementById("reResetBtn").disabled = disabled;

      if (!question) {
        reQuestionWrapEl.classList.add("hidden");
        reNoQuestionTextEl.classList.remove("hidden");
        return;
      }

      reQuestionWrapEl.classList.remove("hidden");
      reNoQuestionTextEl.classList.add("hidden");
      reQuestionMetaEl.textContent = `question_id: ${question.question_id || "-"} | event_type: ${question.event_type || "-"}`;
      reQuestionTextEl.textContent = question.question_text || "";
      const seqWrap = document.getElementById("reSequenceWrap");
      const repeatWrap = document.getElementById("reRepeatCountWrap");
      const seqRequired = !!question.requires_sequence_number;
      const repeatable = !!question.repeatable;
      const collected = countCollectedEventsForQuestion(question.question_id);
      const target = getRepeatTargetFromHistory(question.question_id);
      repeatWrap.classList.toggle("hidden", !repeatable);
      if (repeatable) {
        if (Number.isFinite(target) && target >= 1) {
          reRepeatCountEl.value = String(Math.max(1, Math.min(10, Math.round(target))));
        } else {
          reRepeatCountEl.value = reRepeatCountEl.value || "1";
        }
      } else {
        reRepeatCountEl.value = "1";
      }
      seqWrap.classList.toggle("hidden", !seqRequired);
      if (seqRequired) {
        const nextSequence = Math.max(1, collected + 1);
        const existing = Number(document.getElementById("reSequenceNumber").value);
        if (!Number.isFinite(existing) || existing < 1) {
          document.getElementById("reSequenceNumber").value = String(Math.min(4, nextSequence));
        }
      } else {
        document.getElementById("reSequenceNumber").value = "";
      }
    }

    export function renderRectEventsFinal(finalized) {
      if (!finalized) {
        reSummaryEl.textContent = "Сбор событий ещё не завершён.";
        reEventsListEl.innerHTML = "";
        reWarningsEl.textContent = "";
        return;
      }

      const confidenceLabelMap = { low: "низкая", medium: "средняя", high: "высокая" };
      const summaryText =
        `Событий: ${finalized.events_count ?? 0}. ` +
        `Сильных событий: ${finalized.strong_events_count ?? 0}. ` +
        `Предварительная уверенность: ${confidenceLabelMap[finalized.confidence_preliminary] || "не определена"}.`;
      reSummaryEl.textContent = summaryText;

      reEventsListEl.innerHTML = "";
      const events = Array.isArray(finalized.events) ? finalized.events : [];
      const eventTypeLabelMap = {
        child_birth: "Рождение ребёнка",
        marriage_start: "Оформление брака",
        divorce_separation: "Развод / разрыв союза",
        death_father: "Смерть отца",
        death_mother: "Смерть матери",
        death_child: "Смерть ребёнка",
        death_spouse: "Смерть супруга",
        death_sibling: "Смерть брата/сестры",
        death_grandparent: "Смерть бабушки/дедушки",
        death_close_person_other: "Смерть близкого человека",
        surgery: "Операция",
        major_accident: "Серьёзная авария",
        violence_trauma: "Травма / насилие",
        imprisonment: "Ограничение свободы",
        military_service: "Военная служба",
        long_hospitalization: "Длительная госпитализация",
        local_relocation: "Ближний переезд",
        long_distance_relocation: "Дальний переезд / эмиграция",
        job_start: "Старт работы",
        job_loss: "Потеря работы",
        career_change: "Смена карьеры",
        profession_change: "Смена профессии",
        business_start: "Запуск бизнеса",
        business_loss: "Потеря бизнеса",
        financial_rise_fall: "Финансовый взлёт/падение",
        inner_crisis_turning_point: "Внутренний кризис",
        custom_major_event: "Другое важное событие",
        children_birth: "Рождение ребёнка",
        death_of_close_person: "Смерть близкого человека",
        surgery_accident_life_risk: "Операция/авария с риском",
        marriage_relationship: "Брак/перелом отношений",
        relocation_emigration: "Переезд/эмиграция",
        education_work_start: "Старт учёбы/работы",
        profession_lifestyle_change: "Смена профессии/образа жизни",
        freedom_restriction: "Ограничение свободы",
      };
      const lifeAreaLabelMap = {
        family: "семья",
        relationships: "отношения",
        career: "карьера",
        home: "дом/место",
        health: "здоровье",
        finance: "финансы",
        identity: "идентичность",
        other: "другое",
      };
      const datePrecisionLabelMap = {
        exact: "точная",
        month: "месяц",
        year: "год",
        range: "период",
        unknown: "неизвестно",
      };
      if (!events.length) {
        reEventsListEl.classList.remove("timeline");
        reEventsListEl.innerHTML = "<div class='interval-item'>События не собраны.</div>";
      } else {
        reEventsListEl.classList.add("timeline");
        reEventsListEl.innerHTML = "";
        events.forEach((event, idx) => {
          const item = document.createElement("div");
          item.className = "timeline-item";
          item.style.setProperty("--i", String(idx));
          const label = eventTypeLabelMap[event.event_type] || (event.title || "Событие");
          const impact = Number(event.impact_level);
          const strength = Number.isFinite(impact) ? Math.max(0, Math.min(5, Math.round(impact))) : 0;
          const sequenceText = Number.isFinite(Number(event.sequence_number))
            ? ` · повтор №${Number(event.sequence_number)}`
            : "";
          const precision = datePrecisionLabelMap[event.date_precision] || event.date_precision || "—";
          const area = lifeAreaLabelMap[event.life_area] || event.life_area || "—";
          item.innerHTML =
            `<span class="timeline-node"></span>` +
            `<div class="timeline-card">` +
              `<div class="timeline-date">${event.date_text || "—"} <span class="timeline-precision">(${precision})</span></div>` +
              `<div class="timeline-title">${label}</div>` +
              (event.title && event.title !== label ? `<div class="timeline-sub">${event.title}</div>` : "") +
              `<div class="timeline-meta">Сфера: ${area}${sequenceText}</div>` +
              `<div class="timeline-impact"><span class="ti-label">Сила воздействия</span>` +
                `<span class="ti-bar"><i style="width:${strength * 20}%"></i></span>` +
                `<span class="ti-val">${strength || "—"}/5</span></div>` +
              (event.notes ? `<div class="timeline-notes">${event.notes}</div>` : "") +
            `</div>`;
          reEventsListEl.appendChild(item);
        });
      }

      const warnings = Array.isArray(finalized.warnings) ? finalized.warnings : [];
      reWarningsEl.textContent = warnings.length ? `warnings: ${warnings.join(", ")}` : "";
    }

    export function applyRectEventsResponse(data) {
      rectEventsState.rawLastResponse = data;
      if (data && Array.isArray(data.dialog_history)) {
        rectEventsState.dialogHistory = data.dialog_history;
      }
      if (data?.status === "ask_question" && data.question) {
        rectEventsState.currentQuestion = data.question;
        rectEventsState.finalized = null;
      } else if (data?.status === "finalized") {
        rectEventsState.currentQuestion = null;
        rectEventsState.finalized = data;
      } else {
        throw new Error("Неверный формат ответа Stage 2");
      }

      renderRectEventsQuestion();
      renderRectEventsFinal(rectEventsState.finalized);
    }

    export function buildEventsAnswerPayload(userSkipped) {
      const question = rectEventsState.currentQuestion;
      if (!question) {
        throw new Error("Активный вопрос отсутствует");
      }

      const impactRaw = document.getElementById("reImpactLevel").value;
      const repeatCountRaw = document.getElementById("reRepeatCount").value;
      const sequenceRaw = document.getElementById("reSequenceNumber").value;
      const title = document.getElementById("reTitle").value.trim();
      const dateText = document.getElementById("reDateText").value.trim();
      const notes = document.getElementById("reNotes").value.trim();
      return {
        question_id: question.question_id,
        event_type: question.event_type,
        title: title || null,
        date_text: dateText || null,
        impact_level: impactRaw ? Number(impactRaw) : null,
        reversibility: null,
        life_area: null,
        repeat_count: question.repeatable ? Number(repeatCountRaw || 1) : null,
        sequence_number: sequenceRaw ? Number(sequenceRaw) : null,
        notes: notes || null,
        user_skipped: userSkipped,
      };
    }

    export async function startRectEventsFlow() {
      if (rectEventsState.isBusy) {
        return;
      }

      rectEventsState.isBusy = true;
      renderRectEventsQuestion();
      setReStatus("Запускаем Stage 2...");
      showLlmOverlay("Собираем первый вопрос Stage 2...");

      try {
        const res = await fetch("/api/rectification/events/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_base_url: document.getElementById("reApiBaseUrl").value.trim(),
            dialog_history: rectEventsState.dialogHistory,
          }),
        });
        const { jsonPayload, errorText } = await parseResponseBody(res);
        if (!res.ok) {
          throw new Error(errorText);
        }
        if (!jsonPayload) {
          throw new Error("Пустой ответ API");
        }

        applyRectEventsResponse(jsonPayload);
        updateWizardContextFromCurrentStates();
        const eventsCount = jsonPayload.events_collected_count ?? 0;
        if (jsonPayload.status === "finalized") {
          setReStatus(`Сбор завершён. Событий: ${jsonPayload.events_count ?? 0}`);
        } else {
          setReStatus(`Вопрос получен. Уже собрано событий: ${eventsCount}`);
        }
      } catch (err) {
        setReStatus("Ошибка: " + (err?.message || "network error"));
      } finally {
        rectEventsState.isBusy = false;
        hideLlmOverlay();
        renderRectEventsQuestion();
      }
    }

    export async function continueRectEventsFlow(userSkipped) {
      if (rectEventsState.isBusy) {
        return;
      }
      if (!rectEventsState.currentQuestion) {
        setReStatus("Нет активного вопроса. Нажмите «Начать сбор событий».");
        return;
      }

      rectEventsState.isBusy = true;
      renderRectEventsQuestion();
      setReStatus(userSkipped ? "Пропускаем вопрос..." : "Отправляем ответ...");
      showLlmOverlay("Обрабатываем ваш ответ Stage 2...");

      try {
        const res = await fetch("/api/rectification/events/continue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_base_url: document.getElementById("reApiBaseUrl").value.trim(),
            dialog_history: rectEventsState.dialogHistory,
            last_answer: buildEventsAnswerPayload(userSkipped),
          }),
        });
        const { jsonPayload, errorText } = await parseResponseBody(res);
        if (!res.ok) {
          throw new Error(errorText);
        }
        if (!jsonPayload) {
          throw new Error("Пустой ответ API");
        }

        applyRectEventsResponse(jsonPayload);
        updateWizardContextFromCurrentStates();
        if (jsonPayload.status === "ask_question") {
          resetRectEventsInputs();
          const warnings = Array.isArray(jsonPayload.warnings) ? jsonPayload.warnings : [];
          const warningText = warnings.length ? ` [warnings: ${warnings.join(", ")}]` : "";
          setReStatus(`Следующий вопрос получен.${warningText}`);
        } else {
          setReStatus(`Сбор завершён. Событий: ${jsonPayload.events_count ?? 0}`);
        }
      } catch (err) {
        setReStatus("Ошибка: " + (err?.message || "network error"));
      } finally {
        rectEventsState.isBusy = false;
        hideLlmOverlay();
        renderRectEventsQuestion();
      }
    }

    export async function finalizeRectEventsFlow() {
      if (rectEventsState.isBusy) {
        return;
      }

      rectEventsState.isBusy = true;
      renderRectEventsQuestion();
      setReStatus("Завершаем сбор Stage 2...");
      showLlmOverlay("Формируем итоговый events JSON...");

      try {
        const res = await fetch("/api/rectification/events/finalize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_base_url: document.getElementById("reApiBaseUrl").value.trim(),
            dialog_history: rectEventsState.dialogHistory,
          }),
        });
        const { jsonPayload, errorText } = await parseResponseBody(res);
        if (!res.ok) {
          throw new Error(errorText);
        }
        if (!jsonPayload) {
          throw new Error("Пустой ответ API");
        }
        if (jsonPayload.status !== "finalized") {
          throw new Error("Finalize вернул не final формат");
        }

        applyRectEventsResponse(jsonPayload);
        updateWizardContextFromCurrentStates();
        setReStatus(`Сбор завершён. Событий: ${jsonPayload.events_count ?? 0}`);
      } catch (err) {
        setReStatus("Ошибка: " + (err?.message || "network error"));
      } finally {
        rectEventsState.isBusy = false;
        hideLlmOverlay();
        renderRectEventsQuestion();
      }
    }
