# FORMULA_V2_IMPORT_REPORT

## Latest import
- date: `2026-07-05`
- scope:
  - `RECT_MOTHER_DEATH_002_DRAFT`
  - `RECT_SIBLING_DEATH_002_DRAFT`
  - `RECT_GRANDPARENT_DEATH_002_DRAFT`
- mode: explicit expert/test only
- production defaults: unchanged

## Summary table

| Card ID | Event type | Source expected | Imported unique | Golden | Supporting | Context | Duplicate groups | Collapsed duplicates | Conflicts for review | Malformed/skipped |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `RECT_MOTHER_DEATH_002_DRAFT` | `death_mother` | 78 | 78 | 32 | 26 | 20 | 0 | 0 | 0 | 0 |
| `RECT_SIBLING_DEATH_002_DRAFT` | `death_sibling` | 88 | 84 | 34 | 26 | 24 | 4 | 4 | 0 | 0 |
| `RECT_GRANDPARENT_DEATH_002_DRAFT` | `death_grandparent` | 80 | 80 | 32 | 24 | 24 | 0 | 0 | 0 | 0 |

## Per-card reconciliation

### RECT_MOTHER_DEATH_002_DRAFT
- card_id: `RECT_MOTHER_DEATH_002_DRAFT`
- event_type: `death_mother`
- source expected counts:
  - golden: `32`
  - supporting: `26`
  - context: `20`
  - total: `78`
- imported counts:
  - unique imported rules: `78`
  - imported tiers: `32 / 26 / 20`
- duplicate groups: `0`
- collapsed duplicates: `0`
- conflicts_for_review: `0`
- malformed/skipped entries: `0`
- expert note:
  - purpose: Death of mother (draft v2 imported sandbox)
  - expert confirmation needed: clean revised re-import; previous tier conflicts are no longer present in the new source pack.
  - test-mode readiness: `yes`

### RECT_SIBLING_DEATH_002_DRAFT
- card_id: `RECT_SIBLING_DEATH_002_DRAFT`
- event_type: `death_sibling`
- source expected counts:
  - golden: `38`
  - supporting: `26`
  - context: `24`
  - total: `88`
- imported counts:
  - unique imported rules: `84`
  - imported tiers: `34 / 26 / 24`
- duplicate groups: `4`
- collapsed duplicates: `4`
- conflicts_for_review: `0`
- malformed/skipped entries: `0`
- expert note:
  - purpose: Death of sibling (draft v2 imported sandbox)
  - expert confirmation needed: source contains 4 exact same-tier duplicate rule ids; they are collapsed deterministically without semantic conflict.
  - test-mode readiness: `yes`

- duplicate groups detail:
  - `cusp_8_to_cusp_3`: kept `golden`, resolution `kept_first_exact_duplicate`
  - `cusp_3_to_cusp_8`: kept `golden`, resolution `kept_first_exact_duplicate`
  - `cusp_10_to_cusp_3`: kept `golden`, resolution `kept_first_exact_duplicate`
  - `cusp_3_to_cusp_10`: kept `golden`, resolution `kept_first_exact_duplicate`

### RECT_GRANDPARENT_DEATH_002_DRAFT
- card_id: `RECT_GRANDPARENT_DEATH_002_DRAFT`
- event_type: `death_grandparent`
- source expected counts:
  - golden: `32`
  - supporting: `24`
  - context: `24`
  - total: `80`
- imported counts:
  - unique imported rules: `80`
  - imported tiers: `32 / 24 / 24`
- duplicate groups: `0`
- collapsed duplicates: `0`
- conflicts_for_review: `0`
- malformed/skipped entries: `0`
- expert note:
  - purpose: Death of grandparent (draft v2 imported sandbox)
  - expert confirmation needed: clean import; ready for explicit test mode after semantic expert review.
  - test-mode readiness: `yes`

## Import conclusion
- `RECT_MOTHER_DEATH_002_DRAFT`: revised source pack imported cleanly; previous tier conflicts are removed in the new source file
- `RECT_SIBLING_DEATH_002_DRAFT`: structurally valid import; 4 exact same-tier duplicates collapsed deterministically
- `RECT_GRANDPARENT_DEATH_002_DRAFT`: clean import, ready for explicit test mode
