# FORMULA_V2_EXPERT_REVIEW_SUMMARY

## Purpose
This note is the expert-readable handoff for the latest three V2 draft card updates.
It is intended for review before any later live deploy.

## Cards in scope
- `RECT_MOTHER_DEATH_002_DRAFT`
- `RECT_SIBLING_DEATH_002_DRAFT`
- `RECT_GRANDPARENT_DEATH_002_DRAFT`

## Event bindings used in repo
- `RECT_MOTHER_DEATH_002_DRAFT` -> `death_mother`
- `RECT_SIBLING_DEATH_002_DRAFT` -> `death_sibling`
- `RECT_GRANDPARENT_DEATH_002_DRAFT` -> `death_grandparent`

## Expert review summary

### RECT_MOTHER_DEATH_002_DRAFT
- status: clean import
- counts: `78 = 32 golden + 26 supporting + 20 context`
- duplicate groups: `0`
- collapsed duplicates: `0`
- malformed/skipped: `0`
- conflicts_for_review: `0`
- expert action: clean revised re-import; previous tier conflicts are no longer present in the new source pack.
- test-mode readiness: `ready`

### RECT_SIBLING_DEATH_002_DRAFT
- status: clean import
- counts: `84 = 34 golden + 26 supporting + 24 context`
- duplicate groups: `4`
- collapsed duplicates: `4`
- malformed/skipped: `0`
- conflicts_for_review: `0`
- expert action: source contains 4 exact same-tier duplicate rule ids; they are collapsed deterministically without semantic conflict.
- test-mode readiness: `ready`

### RECT_GRANDPARENT_DEATH_002_DRAFT
- status: clean import
- counts: `80 = 32 golden + 24 supporting + 24 context`
- duplicate groups: `0`
- collapsed duplicates: `0`
- malformed/skipped: `0`
- conflicts_for_review: `0`
- expert action: clean import; ready for explicit test mode after semantic expert review.
- test-mode readiness: `ready`

## Deploy-ready checklist
- production defaults remain unchanged
- cards remain explicit-only draft/test mode
- run focused formula-card / Pro endpoint / UI selector tests before deploy
- run full pytest before any deploy command
- verify selector, multi-card combined report, expert tables, and Excel export include the new cards

## Recommendation
- ready for deploy after tests: `yes`
- no deploy performed by this script
