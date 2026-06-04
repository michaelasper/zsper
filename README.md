# Zsper

Zsper is a local-first AI product platform for profiles, CLI workflows,
configuration generation, Brain, RAG, orchestration, documentation, and tests.
It is intentionally separate from local model deployment.

The source of truth for the product direction is
[docs/zsper-local-ai-platform-ultimate-spec.md](docs/zsper-local-ai-platform-ultimate-spec.md).

## Repository Boundary

Zsper is split from `llm-server` before product code exists:

- /Users/michaelasper/source/llm-server owns model deployment and oMLX serving.
- /Users/michaelasper/source/zsper owns profiles, CLI, configs, Brain, RAG, orchestrator, docs, and tests.

Zsper may use `llm-server` only through stable external contracts such as an
environment variable, command template, deploy contract file, or local
OpenAI-compatible HTTP endpoint. It must not import benchmark internals or move
product platform responsibilities into `llm-server`.

See [docs/architecture/repository-boundary.md](docs/architecture/repository-boundary.md)
for the explicit allowed and disallowed dependency forms.
