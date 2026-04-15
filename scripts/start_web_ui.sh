#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="$("${SCRIPT_DIR}/_bootstrap_venv.sh")"
exec "${PYTHON_BIN}" -m uvicorn web_ui.main:app --host "${WEB_UI_HOST:-0.0.0.0}" --port "${WEB_UI_PORT:-8014}"

