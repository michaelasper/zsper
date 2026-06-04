# Out-Of-Order Air/Offline MVP

Source DAG: `docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`

This document tracks air/offline work that is intentionally happening out of
the normal DAG order so the project can be copied to a laptop for travel before
the full Brain/RAG/orchestrator milestones are complete.

## Goal

Make an air profile useful while Gemma 4 12B is still downloading elsewhere:
initialize an isolated offline profile, inspect it, run doctor checks, ingest
local text files, search those local files, and reject networked ingest paths.

## Implemented Out Of Order

- `profile init/show/list/doctor` for work, personal, and air/offline profiles.
- Air/offline defaults: Gemma 4 12B code model metadata, disabled remote access,
  offline network policy, SQLite-local storage mode, and local-small embeddings.
- Profile-local root layout, `profile.json`, registry, and `agent-runs/runs.jsonl`.
- Offline network policy checks that block URLs, SearXNG, hosted model/search/
  extraction APIs, plugin network access, and model artifact downloads.
- `local-file ingest/search` MVP for air profiles:
  - copies UTF-8 local files into `brain/assets/`;
  - writes parsed text into `brain/parsed/`;
  - writes document metadata into `brain/documents/`;
  - appends audit events to `brain/ledgers/documents.jsonl`;
  - performs exact local token search without network calls.
- `./setup.sh --air` out-of-order setup path:
  - creates a project `.venv` wrapper unless `--no-venv` is used;
  - creates or reuses the `air` profile;
  - writes and ingests a profile-local readiness note;
  - verifies `profile doctor` and local search before reporting readiness.
- Air/offline documentation:
  - README quick start for `./setup.sh --air`;
  - how-to guide at `docs/runbooks/air-offline.md`;
  - testing runbook coverage for the setup script.

## Deferred Back To The DAG

- Docling parsing for PDFs, Office files, and complex HTML.
- Chunk records, citation anchors, BM25 indexes, embeddings, dense vectors, and
  hybrid ranking.
- `brain answer` with citation objects.
- Notes/tasks/memory records and UI views.
- Mocked local model endpoint startup and agent-run launch.
- Full integration test at `tests/integration/offline/test_air_offline_flows.py`.
- Portable local model adapter startup for the laptop runtime.

## Current Verification

- `pytest tests/unit/profiles/test_air_profile.py -q`
- `pytest tests/unit/security/test_network_policy.py -q`
- `pytest tests/unit/brain/test_air_file_store.py -q`
- `pytest tests/unit/test_cli_air_profile.py -q`
- `pytest tests/unit/test_setup_air_script.py -q`
- `pytest tests/unit/test_docs_links.py -q`
- `pytest tests/unit -q`
