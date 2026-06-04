# Repository Boundary

This document makes the `zsper` versus `llm-server` boundary explicit before
product code exists. The boundary follows
`docs/zsper-local-ai-platform-ultimate-spec.md`.

## Ownership

- /Users/michaelasper/source/llm-server owns model deployment and oMLX serving.
- /Users/michaelasper/source/zsper owns profiles, CLI, configs, Brain, RAG, orchestrator, docs, and tests.

`llm-server` remains the model-serving system. `zsper` remains the product
platform. The dependency direction is one-way: `zsper` may call an external
model-serving contract, but product code must not depend on `llm-server`
internals.

## Allowed Dependency Forms

Zsper may depend on `llm-server` only through these forms:

- An environment variable such as
  `ZSPER_LLM_SERVER_DIR=/Users/michaelasper/source/llm-server`.
- A command template such as
  `mise -C "$ZSPER_LLM_SERVER_DIR" run prod-start-zsper`.
- A deploy contract file emitted by `llm-server`, such as a future
  `reports/local-server/zsper-endpoint.json`.
- A local OpenAI-compatible HTTP endpoint, such as
  `http://127.0.0.1:9127/v1`.

## Disallowed Dependency Forms

Zsper product code must not use any of these dependency forms:

- importing benchmark internals from `llm-server`.
- importing `benchmarks.local_server`; this is a forbidden import.
- storing profile data in llm-server.
- generating adapters from llm-server.
- adding Brain/RAG/memory/tasks to llm-server.

The practical rule is simple: model serving evidence and oMLX deployment stay in
`llm-server`; profiles, user-facing commands, generated configs, Brain, RAG,
memory, tasks, orchestration, docs, and tests stay in `zsper`.
