# Platform Overview

Source references:

- [Ultimate spec](../zsper-local-ai-platform-ultimate-spec.md)
  (`docs/zsper-local-ai-platform-ultimate-spec.md`)
- [Implementation DAG](../superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md)
  (`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`)
- [Profile modes](profile-modes.md)
  (`docs/architecture/profile-modes.md`)

This document summarizes the platform shape that future implementation tasks
should preserve. The full requirements remain in
`docs/zsper-local-ai-platform-ultimate-spec.md`; the executable build order
remains in
`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`.

## Product Boundary

zsper-brain is the product shell. It owns chat, research, documents,
citations, notes, tasks, memories, agent runs, settings, and the operator-facing
workspace. The web shell is a Next.js app backed by local APIs.

zsper-code is the local model adapter layer and launcher layer. It owns
profile-local generated configs for Zed, OpenCode, Pi, and related harnesses,
plus the profile-local oMLX process record used by
`zsper code start|stop|status|smoke`.

Python owns the CLI, profile resolver, config rendering, RAG, ledgers,
orchestrator, and Brain API. The first Brain API target is FastAPI. Canonical
work and personal storage uses Postgres + pgvector, with Redis and local file
storage where the spec calls for them.

## Core Architecture

- Profiles are the isolation boundary. Work, personal, and air profiles share
  code but never share state. Offline is a network-policy state any profile can
  enter.
- Mutations are mirrored to append-only JSONL ledgers for auditability,
  recovery, and offline troubleshooting.
- Brain retrieval is hybrid BM25 + dense vector search. BM25 protects exact
  matches for paths, commands, identifiers, names, and errors; dense vectors
  protect semantic recall.
- RAG answers that use retrieved context return citation objects with chunk
  anchors, not only formatted prose.
- The orchestrator owns task and run state. Agents launch through tmux so
  desktop and mobile attach flows use the same substrate.
- Hosted model, hosted search, and hosted extraction dependencies are not core
  flows. Local OpenAI-compatible model endpoints, local SearXNG, local Docling,
  and local storage are the default path.

## Seven Spec Phases

### Phase 1: Documentation And Project Baseline

Create the repository orientation layer: README, ownership boundary, Python
package scaffold, test harness, empty CLI groups, and architecture/runbook
baselines. Exit when contributors can run tests and explain why product code
and profile-local oMLX launch belong in Zsper.

### Phase 2: Profiles And Code Adapters

Implement profile init/list/show/doctor plus profile-local adapters for Zed,
OpenCode, Pi, and related tools. Exit when profile isolation and generated
config tests prove work and personal state do not cross.

### Phase 3: Brain Storage And Compose

Render profile-specific local services for Brain: Postgres + pgvector, Redis,
SearXNG, Honcho, FastAPI health, and the Next.js shell starter. Model serving
remains outside Brain Compose.

### Phase 4: Documents And RAG

Add ingestion, Docling parsing, chunking, citation anchors, embeddings, BM25,
dense vectors, hybrid search, and grounded answers. Exit when Markdown, PDFs,
web captures, and repo docs produce inspectable citations.

### Phase 5: Notes, Tasks, Memories

Add local notes, tasks, memory events, Honcho sidecar integration, and workspace
views. Exit when these records are profile-local and their provenance can be
inspected.

### Phase 6: Orchestrator And Agent Runs

Add the first-party task/run service, harness adapters, tmux launch, event
collection, artifact capture, summaries, and Agent Runs UI. Exit when a run can
launch, stream events, attach artifacts, finish, and resume.

### Phase 7: Offline And Security Gates

Enforce offline profile policy, no-network tests, hosted-call detection, remote
access rules, secret redaction, and config patch safeguards. Exit when forbidden
hosted calls, Tailscale Funnel, cross-profile reads, and secret leaks fail tests.
