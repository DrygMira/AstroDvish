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

exec "${PYTHON_BIN}" -m uvicorn web_ui.main:app --host "${WEB_UI_HOST:-0.0.0.0}" --port "${WEB_UI_PORT:-8014}"
