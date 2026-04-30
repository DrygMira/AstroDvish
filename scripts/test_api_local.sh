#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  python3.12 -m venv .venv
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  python3 -m venv .venv
  PYTHON_BIN=".venv/bin/python"
else
  echo "Python 3 is not installed" >&2
  exit 1
fi

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
fi

mkdir -p ephe

if ! "${PYTHON_BIN}" -c "import fastapi, uvicorn, swisseph, httpx, pytest, timezonefinder" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install -r requirements.txt
fi

TEST_API_HOST="${TEST_API_HOST:-127.0.0.1}"
TEST_API_PORT="${TEST_API_PORT:-18013}"
BASE_URL="http://${TEST_API_HOST}:${TEST_API_PORT}"
LOG_FILE="${PROJECT_ROOT}/.pytest_cache/test_api_local_uvicorn.log"

export SWEPH_AUTO_DOWNLOAD=false
export APP_LOG_LEVEL=DEBUG

SERVER_PID=""
cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Starting API for smoke tests on ${BASE_URL} ..."
"${PYTHON_BIN}" -m uvicorn app.main:app --host "${TEST_API_HOST}" --port "${TEST_API_PORT}" >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

echo "Waiting for API startup ..."
"${PYTHON_BIN}" - <<PY
import sys
import time

import httpx

base_url = "${BASE_URL}"
timeout_seconds = 30
started = time.time()

while time.time() - started < timeout_seconds:
    try:
        resp = httpx.get(f"{base_url}/api/v1/chart", timeout=2)
        if resp.status_code in (404, 405, 422):
            print("API is up")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(0.4)

print("API did not start in time", file=sys.stderr)
sys.exit(1)
PY

echo "Running HTTP smoke tests against ${BASE_URL} ..."
"${PYTHON_BIN}" - <<PY
import sys

import httpx

base_url = "${BASE_URL}"
client = httpx.Client(timeout=30)

chart_payload = {
    "datetime_utc": "1984-11-13T11:35:00Z",
    "latitude": 53.9006,
    "longitude": 27.5590,
    "house_system": "P",
    "zodiac_mode": "tropical",
    "sidereal_mode": None,
}
chart_resp = client.post(f"{base_url}/api/v1/chart", json=chart_payload)
if chart_resp.status_code != 200:
    print(f"/api/v1/chart failed: {chart_resp.status_code} {chart_resp.text[:500]}", file=sys.stderr)
    sys.exit(1)
chart_data = chart_resp.json()
if "objects" not in chart_data or "sun" not in chart_data["objects"]:
    print("/api/v1/chart response structure invalid", file=sys.stderr)
    sys.exit(1)

rect_payload = {
    "birth_date_local": "2000-04-16",
    "latitude": 53.9,
    "longitude": 27.56667,
    "house_system": "P",
    "zodiac_mode": "tropical",
    "sidereal_mode": None,
}
rect_resp = client.post(
    f"{base_url}/api/v1/rectification/asc-sign-intervals",
    json=rect_payload,
)
if rect_resp.status_code != 200:
    print(
        f"/api/v1/rectification/asc-sign-intervals failed: "
        f"{rect_resp.status_code} {rect_resp.text[:500]}",
        file=sys.stderr,
    )
    sys.exit(1)
rect_data = rect_resp.json()
intervals = rect_data.get("asc_sign_intervals") or []
if not intervals:
    print("Rectification response has empty asc_sign_intervals", file=sys.stderr)
    sys.exit(1)

print("Smoke tests passed:")
print("- /api/v1/chart")
print("- /api/v1/rectification/asc-sign-intervals")
PY

echo "Done."
