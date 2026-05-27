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
