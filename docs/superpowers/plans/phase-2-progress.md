# Phase 2 Progress

Source DAG: `docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`

This document tracks Phase 2 implementation status for
`PROF-001` through `ISO-001`.

## Implemented

| Task | Status | Evidence |
| --- | --- | --- |
| `PROF-001` Profile Schema | Implemented | `src/zsper/profiles/schema.py`, `tests/unit/profiles/test_schema.py` |
| `PROF-002` Mode Defaults And Invariants | Implemented | `src/zsper/profiles/defaults.py`, `tests/unit/profiles/test_defaults.py` |
| `PROF-003` Profile Root Layout Initializer | Implemented | `src/zsper/profiles/init.py`, `tests/unit/profiles/test_init.py` |
| `PROF-004` Profile Registry | Implemented | `src/zsper/profiles/registry.py`, `tests/unit/profiles/test_registry.py` |
| `PROF-005` Profile Resolver | Implemented | `src/zsper/profiles/resolver.py`, `tests/unit/profiles/test_resolver.py` |
| `SEC-001` Secret Redaction | Implemented | `src/zsper/security/redaction.py`, `tests/unit/security/test_redaction.py` |
| `SEC-002` Network Policy | Implemented | `src/zsper/security/network_policy.py`, `tests/unit/security/test_network_policy.py` |
| `SEC-003` Remote Access Policy | Implemented | `src/zsper/security/remote_policy.py`, `tests/unit/security/test_remote_policy.py` |
| `SEC-004` Hosted Dependency Guard | Implemented | `src/zsper/security/hosted_dependencies.py`, `tests/security/test_hosted_dependency_guard.py` |
| `PROF-006` Profile Doctor | Implemented | `src/zsper/profiles/doctor.py`, `tests/unit/profiles/test_doctor.py` |
| `CLI-001` Profile CLI Commands | Implemented | `src/zsper/cli.py`, `tests/unit/profiles/test_profile_cli.py` |
| `CONF-001` Model Endpoint Records | Implemented | `src/zsper/config/model_endpoint.py`, `tests/unit/config/test_model_endpoint.py` |
| `CODE-001` External `llm-server` Contract | Implemented | `src/zsper/code/llm_server_contract.py`, `tests/unit/code/test_llm_server_contract.py`, `tests/security/test_llm_server_boundary.py` |
| `CONF-002` Profile-Local Config Writer | Implemented | `src/zsper/config/writer.py`, `src/zsper/code/adapters/base.py`, `tests/unit/config/test_writer.py` |
| `ADAPT-001` Zed Adapter | Implemented | `src/zsper/code/adapters/zed.py`, `tests/unit/code/test_zed_adapter.py` |
| `ADAPT-002` OpenCode Adapter | Implemented | `src/zsper/code/adapters/opencode.py`, `tests/unit/code/test_opencode_adapter.py` |
| `ADAPT-003` Pi And little-coder Adapter | Implemented | `src/zsper/code/adapters/pi.py`, `tests/unit/code/test_pi_adapter.py` |
| `ADAPT-004` Hermes Launcher Adapter Config | Implemented | `src/zsper/code/adapters/hermes.py`, `tests/unit/code/test_hermes_adapter_config.py` |
| `CLI-002` Code CLI Commands | Implemented | `src/zsper/code/commands.py`, `tests/unit/code/test_code_cli.py` |
| `ISO-001` Foundation Profile Isolation Gate | Implemented | `tests/integration/test_profile_isolation_foundation.py`, `tests/fixtures/profiles/README.md` |

## Notes

- Existing portable profile work was preserved, then split into the Phase 2
  module boundaries required by the DAG.
- Adapter generation remains profile-local by default. The global patch helper
  exists only as an explicit API and returns redacted diffs with backups.
- `llm-server` remains an external dependency through command templates and the
  local OpenAI-compatible HTTP contract; Zsper product code does not import
  `llm-server` internals.
- The DAG originally named separate profile/code command modules and test files.
  The current implementation keeps the small command handlers in `src/zsper/cli.py`
  and tests them through `tests/unit/profiles/test_profile_cli.py` and
  `tests/unit/code/test_code_cli.py`; this is a file-layout difference, not a
  behavior gap.
- `profile doctor` is intentionally a Phase 2 static profile health check:
  schema, registry consistency, directory layout, writability, network policy,
  remote policy, and hosted integration settings. Database reachability,
  local-model availability, Brain API, web UI, SearXNG, and richer service health
  stay with later Brain/platform health tasks.

## 2026-06-05 Audit Remediation

- Malformed `profile.json` handling now reports `ProfileError` instead of raw
  `KeyError` or `JSONDecodeError`.
- Profile schema validation now rejects missing required fields, wrong field
  types, and empty required strings before profile use.
- `resolve_profile_context` is exported from `zsper.profiles` so callers can use
  the profile plus profile-local path context promised by the DAG.
- Hosted dependency scanning now allows plugin references only when plugin
  metadata declares network behavior, secret requirements, profile scope, and
  disabled-by-default status.
- The test harness now blocks rename/replace writes into the real user home in
  addition to common open, mkdir, copy, and pathlib write APIs.

## Verification Commands

```bash
pytest tests/unit/profiles/test_schema.py -v
pytest tests/unit/profiles/test_defaults.py -v
pytest tests/unit/profiles/test_init.py -v
pytest tests/unit/profiles/test_registry.py -v
pytest tests/unit/profiles/test_resolver.py -v
pytest tests/unit/security/test_redaction.py -v
pytest tests/unit/security/test_network_policy.py -v
pytest tests/unit/security/test_remote_policy.py -v
pytest tests/security/test_hosted_dependency_guard.py -v
pytest tests/unit/profiles/test_doctor.py -v
pytest tests/unit/profiles/test_profile_cli.py -v
pytest tests/unit/config/test_model_endpoint.py -v
pytest tests/unit/code/test_llm_server_contract.py tests/security/test_llm_server_boundary.py -v
pytest tests/unit/config/test_writer.py -v
pytest tests/unit/code/test_zed_adapter.py -v
pytest tests/unit/code/test_opencode_adapter.py -v
pytest tests/unit/code/test_pi_adapter.py -v
pytest tests/unit/code/test_hermes_adapter_config.py -v
pytest tests/unit/code/test_code_cli.py -v
pytest tests/integration/test_profile_isolation_foundation.py -v
pytest -q
```
