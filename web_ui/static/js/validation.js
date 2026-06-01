// Авто-извлечено из main.js — чистые парсеры/валидаторы/конвертеры.
import { PRO_ALLOWED_EVENT_TYPES, PRO_ALLOWED_DATE_PRECISION, PRO_ALLOWED_REVERSIBILITY, PRO_ALLOWED_LIFE_AREAS } from "./constants.js";

    export function parseIsoDateParts(value, fallbackHour = 12) {
      if (typeof value !== "string" || !value) return null;
      const match = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/);
      if (!match) return null;
      return {
        year: Number(match[1]),
        month: Number(match[2]),
        day: Number(match[3]),
        hour: match[4] != null ? Number(match[4]) : fallbackHour,
        minute: match[5] != null ? Number(match[5]) : 0,
        second: match[6] != null ? Number(match[6]) : 0,
      };
    }

    export function normalizeSecondValue(value) {
      const parsed = Number(value);
      if (!Number.isFinite(parsed)) return "00";
      const clamped = Math.max(0, Math.min(59, Math.trunc(parsed)));
      return String(clamped).padStart(2, "0");
    }

    export function parseDateTimeLocalParts(value) {
      if (typeof value !== "string" || !value) return null;
      const match = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2}))?$/);
      if (!match) return null;
      return {
        prefix: match[1],
        second: match[2] || null,
      };
    }

    export function buildDateTimeWithSeconds(value, fallbackSecond = "00", forceSecond = null) {
      const parts = parseDateTimeLocalParts(value);
      if (!parts) return value;
      const second = forceSecond != null
        ? normalizeSecondValue(forceSecond)
        : (parts.second || normalizeSecondValue(fallbackSecond));
      return `${parts.prefix}:${second}`;
    }

    export function normalizeCoordinateNumber(value) {
      if (typeof value === "number" && Number.isFinite(value)) {
        return value;
      }
      if (typeof value !== "string") return null;
      const normalized = value.trim().replace(",", ".");
      if (!normalized) return null;
      const parsed = Number(normalized);
      return Number.isFinite(parsed) ? parsed : null;
    }

    export function parseDmsCoordinate(value, axis) {
      if (typeof value !== "string") return null;
      const raw = value.trim().toUpperCase().replace(",", ".");
      if (!raw) return null;

      const signed = normalizeCoordinateNumber(raw);
      if (signed !== null) {
        return signed;
      }

      const match = raw.match(/^([+-]?\d{1,3})\D+(\d{1,2})\D+(\d{1,2}(?:\.\d+)?)\D*([NSEW])?$/);
      if (!match) return null;

      const degreesRaw = Number(match[1]);
      const minutes = Number(match[2]);
      const seconds = Number(match[3]);
      const hemisphere = match[4] || "";
      if (![degreesRaw, minutes, seconds].every(Number.isFinite)) {
        return null;
      }
      if (minutes < 0 || minutes >= 60 || seconds < 0 || seconds >= 60) {
        return null;
      }
      let sign = degreesRaw < 0 ? -1 : 1;
      if (hemisphere === "S" || hemisphere === "W") {
        sign = -1;
      } else if (hemisphere === "N" || hemisphere === "E") {
        sign = 1;
      }
      const absolute = Math.abs(degreesRaw) + (minutes / 60) + (seconds / 3600);
      const decimal = sign * absolute;
      const limit = axis === "lat" ? 90 : 180;
      if (Math.abs(decimal) > limit) {
        return null;
      }
      return decimal;
    }

    export function decimalToDms(value, axis) {
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return "";
      }
      const hemispherePositive = axis === "lat" ? "N" : "E";
      const hemisphereNegative = axis === "lat" ? "S" : "W";
      const hemisphere = value >= 0 ? hemispherePositive : hemisphereNegative;
      const absValue = Math.abs(value);
      const degrees = Math.floor(absValue);
      const minutesFull = (absValue - degrees) * 60;
      const minutes = Math.floor(minutesFull);
      let seconds = Math.round((minutesFull - minutes) * 60);
      let minutesAdjusted = minutes;
      let degreesAdjusted = degrees;
      if (seconds === 60) {
        seconds = 0;
        minutesAdjusted += 1;
      }
      if (minutesAdjusted === 60) {
        minutesAdjusted = 0;
        degreesAdjusted += 1;
      }
      return `${degreesAdjusted}°${String(minutesAdjusted).padStart(2, "0")}'${String(seconds).padStart(2, "0")}" ${hemisphere}`;
    }

    export function resolveTimezoneOffsetForDisplay(timezoneName, birthDateTimeLocal, birthDateLocal) {
      if (!timezoneName) return null;
      const parts = parseIsoDateParts(birthDateTimeLocal || birthDateLocal, 12);
      if (!parts) return null;
      try {
        const probeDate = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second));
        const formatter = new Intl.DateTimeFormat("en-US", {
          timeZone: timezoneName,
          timeZoneName: "longOffset",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        });
        const zonePart = formatter.formatToParts(probeDate).find((item) => item.type === "timeZoneName")?.value || "";
        if (!zonePart.startsWith("GMT")) return null;
        const normalized = zonePart.replace("GMT", "");
        if (!normalized) return "+00:00";
        const sign = normalized.startsWith("-") ? "-" : "+";
        const clean = normalized.replace(/^[+-]/, "");
        const [hours, minutes = "00"] = clean.split(":");
        return `${sign}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
      } catch {
        return null;
      }
    }

    export function tryParseResponseJson(text) {
      if (!text) return null;
      try {
        return JSON.parse(text);
      } catch {
        return null;
      }
    }

    export function toIsoDate(value) {
      if (!value || typeof value !== "string") return null;
      const maybeDate = value.includes("T") ? value.split("T")[0] : value;
      return /^\d{4}-\d{2}-\d{2}$/.test(maybeDate) ? maybeDate : null;
    }

    export function normalizeProEventCard(event, idx) {
      if (!event || typeof event !== "object") return null;
      const fallbackDate = toIsoDate(event.start_date) || toIsoDate(event.end_date) || "2000-01-01";
      const eventType = PRO_ALLOWED_EVENT_TYPES.has(event.event_type) ? event.event_type : "custom_major_event";
      const datePrecision = PRO_ALLOWED_DATE_PRECISION.has(event.date_precision) ? event.date_precision : "unknown";
      const reversibility = PRO_ALLOWED_REVERSIBILITY.has(event.reversibility) ? event.reversibility : "unknown";
      const lifeArea = PRO_ALLOWED_LIFE_AREAS.has(event.life_area) ? event.life_area : "other";
      const impact = Number(event.impact_level);
      const impactLevel = Number.isFinite(impact) ? Math.min(5, Math.max(1, Math.round(impact))) : 3;

      const normalized = {
        event_id: String(event.event_id || `ui_event_${idx + 1}`),
        life_area: lifeArea,
        event_type: eventType,
        title: String(event.title || "Событие из Stage 2"),
        date_text: String(event.date_text || fallbackDate),
        start_date: toIsoDate(event.start_date) || fallbackDate,
        end_date: toIsoDate(event.end_date) || toIsoDate(event.start_date) || fallbackDate,
        date_precision: datePrecision,
        impact_level: impactLevel,
        reversibility,
        sequence_number: Number.isFinite(Number(event.sequence_number)) ? Math.max(1, Math.round(Number(event.sequence_number))) : null,
        notes: String(event.notes || ""),
        user_skipped: Boolean(event.user_skipped),
      };

      if (!normalized.event_id || !normalized.title || !normalized.date_text) {
        return null;
      }
      return normalized;
    }

