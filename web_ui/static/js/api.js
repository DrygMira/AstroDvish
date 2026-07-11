// Авто-извлечено из main.js (build-split). Модуль: api.
import { rdPromptTextEl } from "./dom.js";
import { tryParseResponseJson } from "./validation.js";
import { extractErrorText, humanizeNonJsonError } from "./format.js";

    export async function parseResponseBody(res) {
      if (res.ok) {
        try {
          const jsonPayload = await res.json();
          return {
            jsonPayload,
            errorText: jsonPayload ? extractErrorText(jsonPayload) : "",
          };
        } catch (_) {
          const text = await res.text();
          const jsonPayload = tryParseResponseJson(text);
          return {
            jsonPayload,
            errorText: jsonPayload ? extractErrorText(jsonPayload) : humanizeNonJsonError(res, text),
          };
        }
      }

      const text = await res.text();
      const jsonPayload = tryParseResponseJson(text);
      return {
        jsonPayload,
        errorText: jsonPayload ? extractErrorText(jsonPayload) : humanizeNonJsonError(res, text),
      };
    }

    export async function fetchWithTimeout(url, options = {}, timeoutMs = 180000) {
      const controller = new AbortController();
      const timerId = setTimeout(() => controller.abort(), timeoutMs);
      try {
        return await fetch(url, {
          ...options,
          signal: controller.signal,
        });
      } catch (err) {
        if (err?.name === "AbortError") {
          throw new Error("Расчёт занял слишком много времени. Попробуйте V1, меньше событий или повторите позже.");
        }
        if (err instanceof TypeError) {
          throw new Error("Соединение с сервером прервалось. Попробуйте повторить позже.");
        }
        throw err;
      } finally {
        clearTimeout(timerId);
      }
    }

    export async function loadPrompt() {
      const res = await fetch("/api/prompt");
      const data = await res.json();
      document.getElementById("promptText").value = data.prompt_text || "";
    }

    export async function loadRectificationPrompt() {
      const res = await fetch("/api/rectification/prompt");
      const data = await res.json();
      if (!res.ok) {
        throw new Error(extractErrorText(data));
      }
      rdPromptTextEl.value = data.prompt_text || "";
    }
