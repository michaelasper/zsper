# Testing Runbook

Source references:

- [Ultimate spec](../zsper-local-ai-platform-ultimate-spec.md)
  (`docs/zsper-local-ai-platform-ultimate-spec.md`)
- [Implementation DAG](../superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md)
  (`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`)

This runbook lists the standard verification commands expected by the DAG.
Some commands are future-facing until their corresponding milestone creates the
service or web package, but the command strings should remain stable unless the
DAG is updated.

## Standard Commands

| Scope | Command | Purpose |
| --- | --- | --- |
| Unit | `pytest tests/unit -v` | fast unit checks |
| Integration | `pytest tests/integration -v` | service and profile integration checks |
| Security | `pytest tests/security -v` | policy, redaction, and isolation gates |
| Web | `npm --prefix apps/brain-web test` | Next.js Brain web flows |
| Full smoke | `zsper profile doctor --profile work && zsper code smoke --profile work && zsper brain status --profile work && zsper agent status --profile work` | full smoke verification |
| Portable setup helper | `./setup.sh --air` | prepare a portable profile and verify local ingest/search |

## Foundation Checks

```bash
pytest --collect-only
```

Purpose: confirm pytest can discover the suite.

```bash
pytest tests/unit/test_docs_boundary.py -v
```

Purpose: verify the repository boundary and stale external serving references.

```bash
pytest tests/unit/test_package.py -v
```

Purpose: verify package metadata, importability, dependency groups, and CLI
entry target.

```bash
pytest tests/unit/test_test_harness.py -v
```

Purpose: verify isolated home/profile fixtures and real-home write guards.

```bash
pytest tests/unit/test_cli_help.py -v
```

Purpose: verify the reserved CLI groups and placeholder commands.

```bash
pytest tests/unit/test_docs_links.py -v
```

Purpose: verify architecture/runbook links and command documentation.

```bash
pytest tests/unit/test_setup_air_script.py -v
```

Purpose: verify the portable setup script against an isolated home and confirm
it can be rerun safely.

## Later Milestone Notes

- Integration tests should start from profile fixtures and never depend on
  personal state from another profile.
- Security tests should fail on hosted model/search/extraction calls in core
  flows, Tailscale Funnel exposure, secret ledger writes, unredacted config
  diffs, and direct agent-state mutation.
- RAG tests should assert citation objects with chunk anchors whenever answers
  use retrieved context.
- Web tests should exercise the actual Next.js Brain workspace, not a marketing
  page.
