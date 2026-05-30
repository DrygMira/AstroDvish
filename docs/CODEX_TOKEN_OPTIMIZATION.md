# CODEX_TOKEN_OPTIMIZATION.md

## Goal
Keep Codex task prompts short, stateful, and non-repetitive.

## Rules
- Do not paste the whole project history into every task.
- Point Codex to `docs/AGENTS.md` for permanent rules.
- Point Codex to `docs/PROJECT_STATE.md` for current state.
- One task should have one main focus.
- Split `fix`, `deploy`, and `proof` into separate tasks when possible.
- Do not mix feature work, deploy, and cleanup in one long prompt unless strictly necessary.
- Store long recurring checklists in docs; reference them from prompts instead of copying them.
- If a task pattern repeats, update the template or docs instead of copying a huge prompt again.

## Prompt Shape
- `Title`
- `Goal`
- `Read first`
- `Do`
- `Do not`
- `Tests`
- `Report`

## Recommended Practice
- Keep prompts specific to the current delta only.
- Reuse the same report format across similar tasks.
- Move stable process rules into `docs/AGENTS.md`.
- Move changing technical state into `docs/PROJECT_STATE.md`.
