# Repository Boundary

This document makes the Zsper-owned product and model-serving boundary
explicit. The boundary follows `docs/zsper-local-ai-platform-ultimate-spec.md`.

## Ownership

- /Users/michaelasper/source/zsper owns profiles, CLI, configs, Brain, RAG, orchestrator, profile-local oMLX launch, local OpenAI-compatible HTTP checks, docs, and tests.

Zsper is the product platform and the launcher for its local model endpoint.
Model serving runtime state belongs under the selected profile root. Brain
services consume the local endpoint as clients. Brain Compose must not include model serving.

## Allowed Serving Forms

Zsper model serving may use only these forms:

- The `omlx` binary on `PATH` or an explicit `ZSPER_OMLX_BIN`.
- A profile-local runtime directory containing PID and launch records.
- A local OpenAI-compatible HTTP endpoint, such as
  `http://127.0.0.1:9127/v1`.

## Disallowed Dependency Forms

Zsper product code must not use any of these dependency forms:

- storing profile data outside the profile root.
- calling a hosted model API in a core flow.
- generated editor configs outside profile-owned paths.
- adding model serving to Brain Compose.
- sharing model runtime state across work, personal, or air profiles.

The practical rule is simple: profiles, user-facing commands, generated
configs, Brain, RAG, memory, tasks, orchestration, profile-local oMLX runtime
records, docs, and tests stay in Zsper.
