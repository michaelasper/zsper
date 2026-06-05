# Phase 3 Progress

Source plan: `docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`

Milestone: M3 Brain Platform

## Status

| Task | Title | Dependencies | Status | Verification | Review | Commit |
| --- | --- | --- | --- | --- | --- | --- |
| BRAIN-001 | Profile-Specific Compose Renderer | ISO-001 | Complete | `pytest tests/unit/brain/test_compose.py -q` -> included in 15 passed slice verification | PASS | `feat(brain): add platform foundation` |
| BRAIN-002 | Postgres And pgvector Schema | BRAIN-001 | Complete | `pytest tests/unit/brain/test_schema_sql.py tests/integration/brain/test_postgres_schema.py -q` -> included in 15 passed slice verification | PASS | `feat(brain): add platform foundation` |
| BRAIN-003 | Redis Runtime Integration | BRAIN-001, BRAIN-002 | Complete | `pytest tests/unit/brain/test_redis.py -q` -> included in 15 passed slice verification | PASS | `feat(brain): add platform foundation` |
| BRAIN-004 | Canonical Ledger Writer | BRAIN-002, SEC-001 | Complete | `pytest tests/unit/brain/test_ledgers.py -q` -> included in 15 passed slice verification | PASS | `feat(brain): add platform foundation` |
| BRAIN-005 | FastAPI Brain API Skeleton | BRAIN-002, BRAIN-003, BRAIN-004, PROF-005 | Complete | `pytest tests/unit/brain/test_api_skeleton.py -q` -> included in 12 passed API verification | PASS | `feat(brain): add api health status settings` |
| BRAIN-006 | Health, Status, And Settings API | BRAIN-005, PROF-006, CODE-001 | Complete | `pytest tests/unit/brain/test_health_status_settings.py -q` -> included in 12 passed API verification | PASS | `feat(brain): add api health status settings` |
| BRAIN-007 | Brain CLI Up Down Status | BRAIN-001, BRAIN-006, FND-004 | Complete | `pytest tests/unit/brain/test_cli.py tests/unit/test_cli_help.py -q` -> 25 passed | PASS | `feat(brain): add cli and web shell` |
| BRAIN-008 | Next.js Brain Web Shell Starter | BRAIN-006 | Complete | `npm --prefix apps/brain-web test` -> 4 passed; `npm --prefix apps/brain-web run build` -> passed | PASS | `feat(brain): add cli and web shell` |
| BRAIN-009 | Brain Context Server Stub | BRAIN-005, ADAPT-001 | Complete | `pytest tests/unit/brain/test_context_server.py tests/unit/code/test_zed_adapter.py -q` -> 6 passed | PASS | `feat(brain): add context server command` |
| GATE-001 | Brain Platform Integration Gate | BRAIN-007, BRAIN-008, BRAIN-009 | Complete | `pytest tests/integration/brain/test_brain_platform_gate.py -q` -> 1 passed | PASS | `test(brain): add platform integration gate` |

## Orchestration Notes

- 2026-06-05: Started Phase 3 from the DAG in dependency order.
- First implementer slice: `BRAIN-001` through `BRAIN-004`, covering Compose
  rendering, schema SQL, Redis runtime configuration, and append-only ledgers.
- 2026-06-05: Reviewer rejected the first slice because `profile_id UUID`
  conflicted with string profile ids emitted by Compose/env; implementer changed
  the schema and migration to `profile_id TEXT` and added a regression test for
  the rendered env contract.
- 2026-06-05: First slice review passed after fix. Local verification:
  `pytest tests/unit/brain/test_compose.py tests/unit/brain/test_schema_sql.py tests/unit/brain/test_redis.py tests/unit/brain/test_ledgers.py tests/integration/brain/test_postgres_schema.py tests/unit/test_phase3_progress_doc.py -q`
  -> 15 passed.
- 2026-06-05: Implemented `BRAIN-005` and `BRAIN-006` as one API slice.
  Reviewer rejected the first pass because request profile roots could be
  ignored and database env could point one profile at another profile's
  database; implementer added regression tests and validation for both
  isolation gaps. Local verification:
  `pytest tests/unit/brain/test_api_skeleton.py tests/unit/brain/test_health_status_settings.py -q`
  -> 12 passed, 1 FastAPI/Starlette TestClient deprecation warning.
- 2026-06-05: Implemented `BRAIN-007` and `BRAIN-008` in parallel after
  `BRAIN-006`. Reviewer passed both slices. Local verification:
  `pytest tests/unit/brain/test_cli.py tests/unit/test_cli_help.py -q` -> 25
  passed; `npm --prefix apps/brain-web test` -> 4 passed; `npm --prefix
  apps/brain-web run build` -> passed.
- 2026-06-05: Implemented and reviewed `BRAIN-009`. Local verification:
  `pytest tests/unit/brain/test_context_server.py tests/unit/code/test_zed_adapter.py -q`
  -> 6 passed; `pytest tests/unit/brain -q` -> 35 passed, 1 FastAPI/Starlette
  TestClient deprecation warning.
- 2026-06-05: Implemented and reviewed `GATE-001`. Reviewer rejected two
  initial gate versions for container service URL and Brain web API wiring
  issues. Final fix uses rendered Compose `.env` values for status checks,
  keeps browser fetches same-origin, routes web `/api/*` calls to Brain API
  server-side, and adds Dockerfiles for Brain API and web services. Local
  verification: `pytest tests/unit/brain/test_compose.py tests/integration/brain/test_brain_platform_gate.py -q`
  -> 3 passed; `npm --prefix apps/brain-web test` -> 5 passed; `npm --prefix
  apps/brain-web run build` -> passed.
- Later parallelization point: after `BRAIN-006`, `BRAIN-008` can proceed
  independently from `BRAIN-007` and `BRAIN-009` as long as file ownership stays
  separate.

## Acceptance Gates

- `zsper brain status` must report profile-scoped service state.
- Brain Compose must include Postgres/pgvector, Redis, SearXNG, Honcho, Brain
  API, and Next.js web, and must exclude `llm-server` model serving.
- Work and personal profile outputs must use distinct roots, database names,
  volumes, ledgers, Redis keys, and logs.
- Mutating records must mirror to profile-local append-only JSONL ledgers with
  secret redaction.
- Core Brain flows must not require hosted model, hosted search, hosted
  extraction, Notion, Linear, Open WebUI, Paperclip, Ruflo, or OpenClaw
  dependencies.
