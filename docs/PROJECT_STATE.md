# PROJECT_STATE.md

## 1. Current focus
AstroDvish / Astra Engine / Pro-ректификация / formula-driven refinement.

## 2. Latest stable deploy
- branch: `codex/shared-birth-context-ui`
- commit: `be3cebf`
- tests: `239 passed, 1 xfailed` at deploy time
- deploy status: deployed
- rollback commit: `2ac5374`
- on server already works:
  - `formula_test_mode` connected to Pro UI
  - `validation_report_table` visible in Pro UI
  - child_birth formula 1 fixed to `square`
  - directed/natal coordinates, angles, orb, orb limit visible in UI
  - literal Formula+Rule DSL, typed rulers, event contribution audit
  - `formula_refinement_results` show working range, best candidate, reference candidate
  - ordinary chart / Expert UI / Technical JSON work

## 3. What is already done
- `formula_test_mode` подключён к Pro UI
- matcher работает `Directed source -> Natal target`
- `validation_report` показывает координаты / углы / орбисы
- `RECT_CHILD_BIRTH_001` обновлён
- `symbolic_1deg_per_year` выбран как MVP-метод
- `formula-driven refinement` добавлен
- `golden/supporting` scoring добавлен
- UI debug добавлен
- `validation_report_table` больше не summary-only
- Pro coarse candidate оставлен как legacy/debug, refinement идёт отдельным слоем

## 4. Current unresolved issue
Методология подтверждена Екатериной: системе не нужно попадать ровно в `22:59:45`, если лучший кандидат лежит внутри валидного экспертного диапазона. Текущий лучший кандидат: `22:57:00`; ручной эталон: `22:59:45`; оба лежат внутри рабочего диапазона. Следующий слой: поддержка нескольких рабочих диапазонов в одном Asc-интервале.

## 5. Current reference case
- birth: `1978-03-19 22:59:45 GMT+05`
- coordinates: `40°14'03" N, 69°41'41" E`
- event: `child_birth`, `2005-11-07`
- golden formulas:
  1. `Directed ruler_4 -> Natal house_element_5 square`
  2. `Directed Sun -> Natal Jupiter sextile`
  3. `Directed cusp_6 -> Natal Sun sextile`

## 6. Important decisions
- MVP direction method = `symbolic_1deg_per_year`
- `solar_arc/progressed Sun` оставлен только `optional/debug`
- comparison = `Directed source -> Natal target`
- major aspects for MVP score: `conjunction`, `opposition`, `square`, `trine`, `sextile`
- MVP orb = `±1°`
- natal targets do not move
- `formula-driven refinement` must scan Asc interval
- formulas participate in selecting time, not only post-check
- Chiron is allowed by role when explicitly used by formula
- `gradarch` excluded from MVP
- formula priorities = `golden`, `supporting`, `context`
- one event with 3 strong formulas = working candidate, not final rectification

## 7. Scoring rules v1
- golden formulas first
- supporting formulas cannot overpower golden formulas
- rank by `golden_matched_count`
- then by `golden_orb_sum`
- then by supporting signals
- event confirmation and time refinement stay separated
- show `score_breakdown` in UI

## 8. Known traps / do not repeat
- test mode worked, but Pro UI used old path
- production card was stale while fixture was correct
- old card had `conjunction` instead of `square`
- UI compressed debug and hid coordinates
- Pro coarse candidate was treated as final
- tests checked exact reference chart but not live Pro candidate path
- candidate selection must be live-path tested

## 9. Current next step
Support multiple `working_time_ranges` in refinement output and UI.
Show for each range:
- `start_local`
- `end_local`
- `candidate_count`
- `best_candidate`
- `golden_matched_count`
- `score`
- `selection_reason`

## 10. Required report format for future Codex tasks
Every future report must include:
- A. what changed
- B. tests
- C. live-path proof if UI/Pro affected
- D. current blocker
- E. next recommended step
- F. deploy/no deploy
- G. rollback if deployed

## 11. Current diagnostic snapshot
- current best candidate in refinement: `22:57:00`
- expert valid range: `22:56:47–23:01:50`
- manual reference time: `22:59:45`
- current best candidate `22:57:00` is inside the valid expert range
- there can be multiple valid working ranges even within a couple of hours
- the system should output a working range plus the best candidate inside it, not force one exact second

## 12. Document rules
- Keep this file short and stateful.
- Update it after every meaningful fix, deploy, or expert feedback.
- If `PROJECT_STATE.md` and `AGENTS.md` conflict:
  - `AGENTS.md` wins for permanent rules
  - `PROJECT_STATE.md` wins for current project state

## 13. Current patch notes
- child_birth card is being migrated to literal DSL fields: `formula`, `rule`, `source`, `target`, `aspect`, `priority`, `role`, `comment`
- reverse formulas must never be auto-created; reverse direction requires a separate literal rule
- stale aspect names must be checked against actual angle; current child_birth fix is `Directed cusp_4 -> Natal Moon = trine`
- multiple rulers must stay visibly typed (`primary_ruler`, `modern_ruler`, etc.) in debug/report output
- refinement now carries per-event contribution audit so Pro does not look like it fits only one child_birth event

## 14. Current workflow layer
- child_birth literal DSL is now expected to carry `formula`, `rule`, `source`, `target`, `source_layer`, `target_layer`, `aspect`, `priority`, `orb_limit`, `meaning`, `comment`
- `source_layer` / `target_layer` must stay explicit; do not infer or auto-swap reverse formulas
- Pro refinement should expose `event_contribution_audit` with `event_type`, `event_date`, `matched_count`, `rejected_count`, `missed_count`, `score`, `contribution_to_final_candidate`
- UI should show a separate block: `Вклад событий в результат`
## 15. Verification snapshot (2026-05-27)
- full pytest: `239 passed, 1 xfailed`
- focused rectification/UI tests: `66 passed`
- local Pro endpoint verification passed for literal DSL / typed rulers / `event_contribution_audit`
- verified in Pro JSON:
  - `formula_refinement_results`
  - `working_time_range`
  - `best_candidate`
  - `reference_time`
  - `validation_report`
  - `event_contribution_audit`
  - literal DSL fields and `ruler_type`
  - `score_breakdown`, `event_confirmation_score`, `time_refinement_score`
- ordinary chart API `/api/v1/chart` returns `200`
- browser/plugin verification:
  - local UI opened
  - Stage 1 final result was reproduced in browser
  - HTML/DOM markers for `validation_report_table`, `Orb limit`, `Formula role`, `contribution_to_final_candidate` are present
  - full rendered Pro result inside browser technical panels is still partially blocked by panel visibility/runtime interaction and should be rechecked before deploy if strict browser proof is required
- current risk before deploy:
  - browser live-path proof for the final rendered Pro block is weaker than API/test proof
- next step:
  - keep live-path proof strict after adding `working_time_ranges`

## 16. Confirmed methodology (Ekaterina, 2026-05-27)
- methodology status: confirmed
- MVP direction method: `symbolic_1deg_per_year`
- comparison: `Directed source -> Natal target`
- natal targets never move
- major aspects in MVP score: `conjunction`, `opposition`, `square`, `trine`, `sextile`
- quincunx stays debug-only
- orb for working MVP checks: `±1°`
- Chiron allowed by role
- `gradarch` excluded
- priorities: `golden`, `supporting`, `context`
- refinement must scan the whole Asc interval
- event formulas participate in choosing time, not only in post-check
- there may be multiple working ranges inside one broader Asc interval

## 17. Local verification snapshot (2026-05-27, no deploy)
- full pytest: `241 passed, 1 xfailed`
- focused tests:
  - `test_rectification_pro_endpoint.py`
  - `test_web_ui_pro_confirmations_ui.py`
  - `test_project_state_doc.py`
  - result: `34 passed`
- refinement now supports `working_time_ranges` plus backward-compatible `working_time_range`
- UI now shows that several working ranges may exist
- next deploy gate:
  - rerun strict browser live-path proof if UI/Pro surface changes again

## 18. Child Birth v2 Draft State
- added safe sandbox card: `RECT_CHILD_BIRTH_002_DRAFT`
- production card `RECT_CHILD_BIRTH_001` remains active and unchanged
- draft `RECT_CHILD_BIRTH_002_DRAFT` is excluded from default production-like event lookup unless explicitly requested by `card_id`
- expanded child_birth v2 pack is still draft-only
- source files imported:
  - `C:\Users\user\Desktop\1  ????.txt`
  - `C:\Users\user\Desktop\2 ????.txt`
- current draft now contains imported child_birth v2 formulas from source files
- imported formulas: `90`
- imported tier counts:
  - `golden = 22`
  - `supporting = 37`
  - `context = 31`
  - `ambiguity_risk = 0`
- malformed legacy source blocks skipped: `21`
- reconciliation:
  - expert expected count = `91`
  - safe unique formulas detected = `90`
  - duplicate groups = `51`
  - collapsed duplicate entries = `54`
  - remaining `91 vs 90` gap = manual count gap for expert review; not a safely reconstructable unique rule
- 5 priority conflicts resolved in draft:
  - `cusp_5_to_cusp_4 = golden`
  - `ruler_5_to_house_element_4 = golden` with note `can be downgraded to supporting`
  - `cusp_5_to_house_element_4 = context`
  - `cusp_5_to_jupiter = supporting`
  - `cusp_4_to_jupiter = supporting`
- v2 literal DSL fields:
  - `formula`, `rule`, `source`, `target`
  - `source_layer`, `target_layer`
  - `allowed_aspects`
  - `priority`, `role`, `meaning`, `comment`
- supported priority tiers in code:
  - `golden`
  - `supporting`
  - `context`
  - `ambiguity_risk`
- validation rules:
  - duplicate `rule_id` values fail load
  - `allowed_aspects` must be a JSON list, not a comma-separated string
- mirror/reverse formulas from Katya files are treated as explicit separate rules, not auto-generated
- production scoring and production card remain unchanged; draft is still not in production flow
- next step:
  - expert review of the reconciled `90`-formula draft and the remaining `91 vs 90` manual-count gap
  - validation of `RECT_CHILD_BIRTH_002_DRAFT` on multiple child_birth charts

## 19. Live Deploy Verification (2026-05-28)
- full pytest: `252 passed, 1 xfailed`
- public live health:
  - `/health = 200`
  - public `/api/v1/health = 404` on `45.133.17.16` (not exposed through the public route)
- live Pro endpoint verification: passed
  - `formula_refinement_results`, `working_time_ranges`, `best_candidate`, `reference_time`, `validation_report`, `event_contribution_audit` present
  - direction method in live Pro response: `symbolic_1deg_per_year`
  - production card in live path: `RECT_CHILD_BIRTH_001`
  - production source path in live path: `/opt/astro-bot-api/product/astrobot_content_pack/formula_cards/rectification/RECT_CHILD_BIRTH_001.json`
  - draft card `RECT_CHILD_BIRTH_002_DRAFT` not used in production path without explicit request
  - `ruler_type`, `event_confirmation_score`, `time_refinement_score` present
- live browser/UI smoke:
  - confirmed in live UI: Stage 1 dialog opens and reaches final result
  - confirmed in live UI: Stage 2 preset events render on screen
  - confirmed in served live HTML/DOM markers: `working_time_ranges`, `validation_report_table`, `Directed longitude`, `Natal longitude`, `Orb limit`, `Вклад событий в результат`, `rpRawBox`
  - final rendered live Pro block after full UI click-through still needs one more strict browser proof if required as a release gate
- current release note:
  - live deploy is server-healthy and API-verified
  - browser proof is strong for Stage 1 / Stage 2 and for rendered UI markers, but weaker for final Pro result block
- next step:
  - if strict expert-review gate requires it, rerun one more browser proof for the final rendered Pro panel on live site and capture the visible Pro result block

## 20. Local v2 Draft Comparison Layer (2026-05-28, no deploy)
- `RECT_CHILD_BIRTH_002_DRAFT` is selectable explicitly in Pro / `formula_test_mode` by `formula_card_id`
- production default remains `RECT_CHILD_BIRTH_001` when no explicit card is selected
- local comparison mode can request:
  - baseline `RECT_CHILD_BIRTH_001`
  - selected `RECT_CHILD_BIRTH_002_DRAFT`
- comparison payload now exposes:
  - `formula_card_comparison`
  - `working_time_ranges_difference`
  - `best_candidate_difference`
  - `event_contribution_audit_difference`
- Pro/local UI now shows:
  - selected `card_id`
  - `card_version`
  - `formulas_count`
  - `priority_counts` split into `golden`, `supporting`, `context`, `ambiguity_risk`
  - `V1 vs V2` comparison block
- draft card is still test-only and is not part of default production flow without explicit request

## 21. Strict Live Browser Proof Status (2026-05-28, no deploy)
- public health:
  - `/health = 200`
  - public `/api/v1/health = 404`
- current interpretation:
  - public canonical health endpoint is `/health`
  - `/api/v1/health` is not exposed through the current public reverse-proxy path
- live Pro JSON verification with reference-like child_birth payload works through public UI proxy when `api_base_url = http://127.0.0.1:8013`
- verified in live Pro JSON:
  - `formula_refinement_results`
  - `working_time_ranges`
  - `best_candidate`
  - `reference_time`
  - `validation_report`
  - `event_contribution_audit`
  - literal DSL fields `formula` / `rule`
  - `ruler_type`
  - `direction_method = symbolic_1deg_per_year`
  - production card stays `RECT_CHILD_BIRTH_001`
  - draft card `RECT_CHILD_BIRTH_002_DRAFT` stays inactive unless explicitly requested
  - `Directed cusp_4 -> Natal Moon` is `trine`, not `conjunction`
- strict browser proof result:
  - failed as a release gate
  - live browser plugin can read DOM and markers, but final interactive Pro screen was not reproducibly rendered end-to-end in this proof run
  - ordinary chart modal also did not open during browser-plugin proof, so current blocker is browser-proof completeness, not backend JSON completeness
- next step:
  - rerun final live browser proof with a reproducible manual/browser path to the rendered Pro result block before handing off to Ekaterina as fully browser-verified

## 22. Reliable Local UI Proof Mode (2026-05-28, no deploy)
- added deterministic preview mode for browser/plugin proof:
  - `?proof_preview=pro` -> renders final Pro panel from fixture response
  - `?proof_preview=chart` -> opens ordinary chart modal from fixture response
  - `?proof_preview=all` -> runs both previews
- added preview endpoints:
  - `/api/preview/pro-result`
  - `/api/preview/chart-result`
- purpose:
  - prove final rendered UI blocks without fragile Stage1/Stage2 interaction dependency
  - keep astrological logic and formula cards unchanged
- public health decision unchanged:
  - `/health` is the public health endpoint
  - `/api/v1/health` is treated as internal/not publicly routed on current gateway

## 23. Resolver Precision Cleanup (2026-05-28, no deploy)
- Ekaterina feedback captured:
  - some rules showed widened targets/rulers in debug
  - `cusp_10 -> cusp_5` can be geometrically closer to another major aspect than configured narrow aspect
- cleanup target:
  - strict literal selector filtering from `source` / `target` fields
  - no silent mixing of `cusp_N` and `significators` inside one resolved target group
  - ruler resolution supports `allowed_ruler_types` and reports `ruler_type`
  - validation report debug shows selector include/exclude reasons, source/target groups, and closest-major-aspect mismatch warnings
- production flow unchanged:
  - no activation switch
  - no direction math core change

## 24. Resolver Cleanup Verification Snapshot (2026-05-28, no deploy)
- resolver precision cleaned up:
  - literal `target=cusp_N` now resolves only to natal `cusp_N`
  - literal `target=house_element_N` resolves only to natal house elements of house `N`
  - `significators` stay isolated and are not silently mixed into `cusp_N` target rows
  - validation debug now shows `resolved_source_group`, `resolved_target_group`, `source_type`, `target_type`, selector include/exclude reasons, and ruler resolution reasons
- ruler precision cleaned up:
  - rules can restrict `allowed_ruler_types`
  - current child_birth production card metadata uses `allowed_ruler_types=["modern_ruler"]` for `ruler_4_to_house_element_5`, so Neptune is scored and Jupiter is excluded for this rule
  - excluded rulers are now visible in debug with reason
- aspect mismatch policy:
  - no core math change
  - no blind production aspect rewrite
  - if actual geometry is closer to another major aspect, report now shows `closest_major_aspect_mismatch` with configured aspect, closest major aspect, actual angle, exact angle, orb to configured, orb to closest
  - current open expert decision remains `cusp_10 -> cusp_5`: keep narrow rule + warning, or switch to `opposition`, or move to `allowed_aspects`
- preview fixture sync:
  - `web_ui/fixtures/pro_result_preview.json` synced with real Pro JSON shape
  - preview now carries `ruler_type`, resolver groups, include/exclude reasons, mismatch warning, literal Formula/Rule fields, and `event_contribution_audit`
- local proof status:
  - focused tests: `88 passed`
  - full pytest: `262 passed, 1 xfailed`
  - fresh local UI proof run on `http://127.0.0.1:8015/?proof_preview=pro|chart|all`
  - Pro preview visibly shows working ranges, best/reference candidate, formula table columns with coordinates/angles/orbs, raw JSON, and keeps default card `RECT_CHILD_BIRTH_001`
  - chart preview visibly opens modal, expert table, and raw API JSON
- draft status:
  - `RECT_CHILD_BIRTH_002_DRAFT` still exists but is not activated in default production flow
- next step:
  - get Ekaterina decision on `cusp_10 -> cusp_5` aspect policy
  - then do one more live/server proof before deploy

## 25. Ekaterina Confirmation Applied Locally (2026-05-28, no deploy)
- expert confirmation applied to policy layer only; no direction math/core change
- production card `RECT_CHILD_BIRTH_001` updated locally:
  - `Directed cusp_10 -> Natal cusp_5` now uses `opposition` instead of `trine`
  - the old `closest_major_aspect_mismatch` warning for this exact rule is removed; production path should now show `opposition` and, if outside orb, `rejected/over_orb`
  - `allowed_ruler_types=["modern_ruler"]` remains on `ruler_4_to_house_element_5`, so Neptune stays included and Jupiter stays excluded for this rule
- significators policy clarified:
  - significators are stable card metadata, not dynamic house-ruler substitutions
  - if a formula explicitly names a planet, resolver uses that planet only
  - if a formula explicitly uses `significators`, resolver uses only configured significators and does not mix them with `cusp_N`
- v2 / draft policy:
  - draft formulas continue to use explicit `allowed_aspects` major list only:
    `conjunction`, `square`, `opposition`, `trine`, `sextile`
  - this major-list policy is for v2/draft DSL and is not auto-expanded across all production v1 rules
- preview sync:
  - `web_ui/fixtures/pro_result_preview.json` now mirrors the updated policy:
    `cusp_10 -> cusp_5` is shown as `opposition`
    it remains visible as expected/rejected by orb when outside the current production orb limit
- metadata naming:
  - misleading production `card_version=child_birth_solar_arc_v2` renamed locally to `child_birth_symbolic_mvp_v3`
  - notes now explicitly say `symbolic_1deg_per_year` MVP and that `cusp_10 -> cusp_5` is `opposition` with preserved `over_orb` behavior
- deploy state:
  - this production-card change is local only and still pending deploy
