# Rectification Engine Pro (MVP)

## Purpose

`Rectification Engine Pro` builds and scores birth-time hypotheses using:

- Stage 1 Asc windows,
- Stage 2 life events,
- multi-method validation pipeline.

Output is **probabilistic candidate windows** with confidence metadata, not guaranteed exact birth time.

## Implemented modules (MVP)

- `candidate_generator`: generates candidate times inside Asc windows.
- `directions_service`: symbolic progression proxy (1° = 1 year), major aspect matching.
- `solar_service`: lightweight annual solar validation proxy.
- `lunar_service`: placeholder (optional, bounded, low-weight).
- `transit_service`: exact-date transit check proxy (non-exact dates -> warning).
- `totem_service`: technical Asc degree index only, no copyrighted text DB.
- `scoring_service`: weighted merge of method scores.
- `confidence_service`: low/medium/high/expert_high gating rules.

## API

- Endpoint: `POST /api/v1/rectification/pro/run`
- Web UI proxy: `POST /api/rectification/pro/run`

See examples:

- `docs/examples/rectification_pro_request.json`
- `docs/examples/rectification_pro_response.json`

## Confidence policy

- `low`: sparse evidence, broad windows.
- `medium`: useful windows, but not enough exact-event support for minute precision.
- `high`: stronger multi-method evidence; may allow ~5–10 minute working window.
- `expert_high`: only when strict criteria are met (enough events, strong events, exact dates, multi-method support).

## Limitations

- MVP uses deterministic proxy scoring, not full human-master rectification.
- Lunar module is placeholder.
- Totem semantic database is not connected.
- Should be used as a structured narrowing engine, not an oracle of exact birth time.
