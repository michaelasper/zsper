# Local Development Runbook

Source references:

- [Ultimate spec](../zsper-local-ai-platform-ultimate-spec.md)
  (`docs/zsper-local-ai-platform-ultimate-spec.md`)
- [Implementation DAG](../superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md)
  (`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`)
- [Offline state runbook](offline-state.md)
  (`docs/runbooks/offline-state.md`)

Use this runbook for local development in `/Users/michaelasper/source/zsper`.
The project is local-first and profile-isolated; avoid commands that write into
the real user home unless a later task explicitly adds a guarded profile write.

## Orientation

1. Confirm you are in the Zsper repository:

   ```bash
   pwd
   ```

   Purpose: expected output is `/Users/michaelasper/source/zsper`.

2. Inspect current changes before editing:

   ```bash
   git status --short --branch
   ```

   Purpose: identify user changes so implementation work does not revert them.

3. Use `rg` before broad reads:

   ```bash
   rg -n "FND-005|Phase 1|profile isolation|llm-server" docs src tests
   ```

   Purpose: find the relevant local context without rereading the whole spec.

## Foundation Commands

```bash
pytest --collect-only
```

Purpose: verify the Python test runner can discover the suite.

```bash
pytest tests/unit -v
```

Purpose: run fast unit checks during Phase 1 and later implementation tasks.

```bash
python -m zsper --help
```

Purpose: verify the CLI package entry point exposes the reserved command groups.

```bash
./setup.sh --air --name portable
```

Purpose: prepare a portable air profile in offline state and verify local file
ingest/search without hosted calls.

## Development Rules

- Keep Zsper product code in `/Users/michaelasper/source/zsper`.
- Treat `/Users/michaelasper/source/llm-server` as a model-serving dependency
  reachable through commands, endpoint metadata, or local OpenAI-compatible
  HTTP; do not import its benchmark internals.
- Keep generated configs and runtime files profile-local by default.
- Keep Brain services local. `zsper-brain` is the product shell; `zsper-code` is
  the local model adapter layer.
- Prefer FastAPI for Brain API work, Next.js for Brain web work, Postgres +
  pgvector for canonical storage, and hybrid BM25 + dense retrieval for RAG.
- Launch agent runs through tmux and mirror mutations to append-only JSONL
  ledgers when those phases are implemented.
