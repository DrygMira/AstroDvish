#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="$("${SCRIPT_DIR}/_bootstrap_venv.sh")"

export SWEPH_AUTO_DOWNLOAD=false
export APP_LOG_LEVEL=DEBUG
exec "${PYTHON_BIN}" -m uvicorn app.main:app --host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-8013}"

