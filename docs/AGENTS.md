# AGENTS.md

## Project Identity
- Project: `AstroDvish / GlobaAstro / Digital Astrologer`
- Current product target: `Beta preliminary rectification`
- Expert precise rectification is future R&D, not the current blocker

## Safety Rules
- Do not change astrology core math unless the task explicitly says so.
- Do not activate `RECT_CHILD_BIRTH_002_DRAFT` by default.
- `RECT_CHILD_BIRTH_001` remains the production default unless a task explicitly changes it.
- V2 draft is explicit expert/test mode only.
- Do not deploy unless the task explicitly says deploy.
- If deploy is requested, always include the rollback commit in the report.
- Do not silently overwrite formula rules.
- Do not auto-generate reverse formulas unless explicitly requested.
- Do not hide unresolved or conflict cases; report them.

## Encoding And Editing Rules
- Files with Russian or Cyrillic text must be edited safely with direct file editing tools.
- Avoid shell replace one-liners that can corrupt encoding.
- Do not normalize mojibake unless the task explicitly asks for cleanup.

## Formula Card Rules
- Formula DSL fields:
  - `formula`
  - `rule`
  - `source`
  - `source_layer`
  - `target`
  - `target_layer`
  - `allowed_aspects`
  - `priority`
  - `role`
  - `meaning`
  - `comment`
- `allowed_aspects` must be a JSON list, not a comma-separated string.
- Priority tiers:
  - `golden`
  - `supporting`
  - `context`
  - `ambiguity_risk`
- `target=cusp_N` must resolve only `cusp_N`.
- An explicit planet must not expand into generic significators.
- Significators are stable; rulers change by candidate chart.
- `ruler_N` must respect `allowed_ruler_types` when provided.
- Context can contribute with lower weight, but must not overpower `golden` or `supporting`.
- `ambiguity_risk` should warn or penalize, not break evaluation.

## Current Cards
- `RECT_CHILD_BIRTH_001` = production default
- `RECT_CHILD_BIRTH_002_DRAFT` = v2 draft, expert/test only
- Treat v2 draft as a v1 superset with `inherited_from_v1` rules unless `docs/PROJECT_STATE.md` says otherwise

## Testing Rules
- Always run focused tests for the touched area.
- Run full `pytest` before `ready for deploy = yes`.
- For UI or proof changes, include browser proof or preview proof where applicable.
- Heavy Pro runs must be tested with both `1 event` and `multi-event` payloads when relevant.
- Report `performance_debug` for heavy rectification work.

## Reporting Format
- Keep reports maximum short.
- Default report shape:
  - `A.` what changed or root cause
  - `B.` tests
  - `C.` live or proof status if applicable
  - `D.` production card status
  - `E.` draft card status
  - `F.` risks
  - `G.` ready for deploy yes/no
  - `H.` no deploy or deploy confirmation
  - `I.` rollback if deployed

## Working Model
- Read this file first for permanent rules.
- Read `docs/PROJECT_STATE.md` second for current project state.
- Keep future task prompts short; do not paste long historical context if the same rule already lives here or in `docs/PROJECT_STATE.md`.
