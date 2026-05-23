# PROJECT_STATE.md

## 1. Current focus
AstroDvish / Astra Engine / Pro-ректификация / formula-driven refinement.

## 2. Latest stable deploy
- branch: `codex/shared-birth-context-ui`
- commit: `5b47ed4`
- tests: `226 passed, 1 xfailed` at deploy time
- deploy status: deployed
- rollback commit: `ae80810`
- on server already works:
  - `formula_test_mode` connected to Pro UI
  - `validation_report_table` visible in Pro UI
  - child_birth formula 1 fixed to `square`
  - directed/natal coordinates, angles, orb, orb limit visible in UI
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
Refinement уже сканирует Asc-интервал и выбирает кандидата по golden formulas, но эталон `22:59:45` пока не выбран. Текущий лучший кандидат: `22:57:00`, потому что у него лучше `golden_orb_sum`.

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
- natal targets do not move
- `formula-driven refinement` must scan Asc interval
- formulas participate in selecting time, not only post-check
- one event with 3 strong formulas = working candidate, not final rectification

## 7. Scoring rules v1
- golden formulas first
- supporting formulas cannot overpower golden formulas
- rank by `golden_matched_count`
- then by `golden_orb_sum`
- then by supporting signals
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
Generate candidate comparison table around child_birth reference time from `22:55:00` to `23:00:30` with `30s` step.
Show:
- candidate time
- golden matched count
- each golden formula orb
- `golden_orb_sum`
- supporting matched count
- final score
- why candidate wins
- compare `22:57:00` vs `22:59:45`

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
- old pre-golden best: `22:56:30`
- reference time `22:59:45` still has `3/3` golden matches, but worse `golden_orb_sum`
- best individual golden orbs currently split across different times:
  - `Neptune -> Mercury`: best near `22:55:00`
  - `Sun -> Jupiter`: best near `23:00:30`
  - `cusp_6 -> Sun`: best at `22:57:00`
- this means expert decision is still needed on whether formula 3 should dominate candidate selection that strongly

## 12. Document rules
- Keep this file short and stateful.
- Update it after every meaningful fix, deploy, or expert feedback.
- If `PROJECT_STATE.md` and `AGENTS.md` conflict:
  - `AGENTS.md` wins for permanent rules
  - `PROJECT_STATE.md` wins for current project state
