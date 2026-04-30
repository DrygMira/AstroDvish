# CURRENT_STATE

## Project Structure (actual)
- `app/` FastAPI calculation API (`/api/v1/chart`, `/api/v1/rectification/asc-sign-intervals`)
- `web_ui/` separate FastAPI UI backend + static UI for chart + Stage 1 rectification dialog
- `tests/` API tests (chart validation/success, ephemeris bootstrap, asc-sign-intervals)
- `scripts/` local run scripts for API/UI/smoke
- `docker-compose.yml` currently starts only API container

## Local Run (from code/scripts)
- API: `./scripts/start_api_local.sh` (uvicorn `app.main:app`, default `:8013`)
- Web UI: `./scripts/start_web_ui.sh` (uvicorn `web_ui.main:app`, default `:8014`)
- Smoke: `./scripts/test_api_local.sh`

## Real Endpoints Found
### API (`app`)
- `POST /api/v1/chart`
- `POST /api/v1/rectification/asc-sign-intervals`

### Web UI backend (`web_ui`)
- `GET /`
- `GET /api/prompt`
- `GET /api/rectification/prompt`
- `POST /api/geocode`
- `POST /api/generate`
- `POST /api/rectification/asc-sign-intervals`
- `POST /api/rectification/dialog/start`
- `POST /api/rectification/dialog/continue`
- `GET /static/{filename}`

## Environment Variables (actual)
From `.env.example` + code:
- `APP_NAME`, `APP_HOST`, `APP_PORT`, `APP_LOG_LEVEL`
- `SWEPH_EPHE_PATH`, `SWEPH_AUTO_DOWNLOAD`, `SWEPH_DOWNLOAD_TIMEOUT`, `SWEPH_DOWNLOAD_RETRIES`, `SWEPH_DOWNLOAD_BASE_URLS`
- For web-ui local ports: `WEB_UI_HOST`, `WEB_UI_PORT` (used by script)
- For OpenAI calls in web_ui: `secrets.txt` with `OPENAI_API_KEY=...` (not env-based)

## Tests Present
- `tests/test_chart_success.py`
- `tests/test_chart_validation.py`
- `tests/test_ephe_bootstrap.py`
- `tests/test_rectification_endpoint.py`

## Reproducible Risks / Problems (before changes)
- Stage 1 dialog strongly depends on LLM output shape; malformed JSON or weak structure can break flow.
- `ask_question` can be unusable (e.g., empty/bad options), causing UX dead-end.
- No dedicated API health endpoints (`/health`, `/api/v1/health`).
- No request_id propagation and no request-scoped structured logs.
- `docker-compose` covers API only, not web UI.
- README is partially outdated vs real endpoint surface and runtime behavior.
- Free-text contract mismatch: `allow_free_text` exists but UI path effectively sends `free_text: null`.

## Current Verification Status in this session
- Unable to execute `pytest` baseline in this environment: `python`, `py`, and `docker` executables are not available in current shell session.

## Scope of changes in this task
- Stabilization only (no Stage 2/events/transits/solars/lunars/totems/main AstroBot integration)
- Keep existing endpoints compatible
- Add guard/fallback for Stage 1 dialog
- Add health endpoints + request_id logging
- Improve docker-compose coverage/documentation
- Add tests for guard/fallback + health + non-mixing invariants
