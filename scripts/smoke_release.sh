#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8013}"
TIMEOUT_SEC="${TIMEOUT_SEC:-30}"
FAIL_COUNT=0

run_check() {
  local name="$1"
  shift
  echo "[$name] running..."
  if "$@"; then
    echo "[$name] OK"
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "[$name] FAIL"
  fi
}

check_health() {
  local body
  body="$(curl -sS -m "${TIMEOUT_SEC}" \
    -H "X-Request-ID: smoke-health-$(date +%s)" \
    "${API_BASE_URL}/health")"
  echo "${body}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="ok"; assert d["service"]=="astrodvish-api"; assert d["version"]=="0.5.0"'
}

check_api_v1_health() {
  local body
  body="$(curl -sS -m "${TIMEOUT_SEC}" \
    -H "X-Request-ID: smoke-api-v1-health-$(date +%s)" \
    "${API_BASE_URL}/api/v1/health")"
  echo "${body}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="ok"; assert d["service"]=="astrodvish-api"; assert d["version"]=="0.5.0"'
}

check_chart() {
  local body
  body="$(curl -sS -m "${TIMEOUT_SEC}" -X POST \
    -H "Content-Type: application/json" \
    -H "X-Request-ID: smoke-chart-$(date +%s)" \
    "${API_BASE_URL}/api/v1/chart" \
    -d '{"datetime_utc":"1984-11-13T11:35:00Z","latitude":53.9006,"longitude":27.5590,"house_system":"P","zodiac_mode":"tropical","sidereal_mode":null}')"
  echo "${body}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "objects" in d and "sun" in d["objects"]; assert "aspects" in d'
}

check_asc_intervals() {
  local body
  body="$(curl -sS -m "${TIMEOUT_SEC}" -X POST \
    -H "Content-Type: application/json" \
    -H "X-Request-ID: smoke-rect-$(date +%s)" \
    "${API_BASE_URL}/api/v1/rectification/asc-sign-intervals" \
    -d '{"birth_date_local":"2000-04-16","latitude":53.9,"longitude":27.56667,"house_system":"P","zodiac_mode":"tropical","sidereal_mode":null}')"
  echo "${body}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["birth_context"]["timezone"]; assert d["birth_context"]["timezone_source"]=="coordinates"; assert len(d["asc_sign_intervals"])>0'
}

check_events_start() {
  local body
  body="$(curl -sS -m "${TIMEOUT_SEC}" -X POST \
    -H "Content-Type: application/json" \
    -H "X-Request-ID: smoke-events-$(date +%s)" \
    "${API_BASE_URL}/api/v1/rectification/events/start" \
    -d '{"dialog_history":[]}')"
  echo "${body}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"] in ("ask_question","finalized")'
}

run_check "health" check_health
run_check "api-v1-health" check_api_v1_health
run_check "chart" check_chart
run_check "asc-sign-intervals" check_asc_intervals
run_check "events-start" check_events_start

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo ""
  echo "Smoke release checks FAILED: ${FAIL_COUNT}"
  exit 1
fi

echo ""
echo "Smoke release checks PASSED"
