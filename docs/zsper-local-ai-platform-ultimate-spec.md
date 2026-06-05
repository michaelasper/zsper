# Zsper Local AI Platform Ultimate Spec

Date: 2026-06-04

## Executive Summary

Zsper is a local-first AI platform split across two repositories with a strict
responsibility boundary:

- `~/source/llm-server` owns local model deployment. For the first production
  target, it starts and manages the oMLX OpenAI-compatible endpoint on
  `127.0.0.1:9127`.
- `~/source/zsper` owns the product platform. It manages profiles, client
  configs, chat, research, local document RAG, memory, notes, tasks, agent
  orchestration, local API services, and the custom web shell.

The platform must run as two reusable but separately deployable local systems:

- `zsper-code`: coding-focused local model access and editor/agent adapters.
- `zsper-brain`: custom local shell for chat, research, documents, citations,
  notes, tasks, memories, and agent orchestration.

Every install is isolated. Work and personal profiles use the same codebase and
deployment shape, but they must never share data roots, databases, secrets,
model configs, agent histories, memory stores, document indexes, task ledgers,
or generated client configs. Air mode uses a smaller code-only model profile.
Offline is a network-policy state that can disable network-dependent flows for
any profile.

The system is local-first and no SaaS integration is a core dependency. Notion,
Linear, hosted search, hosted model APIs, hosted extraction services, Open WebUI,
Paperclip, Ruflo, and OpenClaw are future adapters or reference material, not
foundational runtime dependencies.

## Multi-Agent Design Synthesis

This spec was composed by treating the project as a multi-agent design problem
and synthesizing the following specialist perspectives into one architecture.

### Product Architect Perspective

The product should begin as a real usable local shell, not a benchmark harness or
collection of scripts. The first screen should be an authenticated local
workspace with chat, documents, research inbox, notes, tasks, memories, and
agent runs. The user should not have to understand model server internals to use
Zsper. They should choose a profile, start code serving, start brain services,
and then work in the web shell or terminal agents.

Decision: Zsper is profile-centric. Every CLI command takes `--profile <name>` or
resolves a default profile. Profiles are the top-level unit of isolation,
configuration, and observability.

### Local Inference Engineer Perspective

The local model server has already been worked out in `llm-server`. Rebuilding
or embedding that code in `zsper` would duplicate responsibilities and make
future engine swaps harder. Zsper should depend on a stable serving contract:
OpenAI-compatible HTTP, model id, base URL, context window, output limit, tool
support, health endpoint, and smoke test.

Decision: Zsper does not import `benchmarks.local_server` as product internals.
It can call `llm-server` through a subprocess, a declared command contract, or a
small adapter script, but the model server remains an external dependency. The
primary interface is:

```text
base_url: http://127.0.0.1:9127/v1
primary_model: zsper-qwen35-oq6-fp16-mtp-omlx-128k
personal_long_context_fallback: zsper-qwen35-oq6-omlx-256k
air_model: zsper-air-gemma4-12b-it-6bit-128k
```

### Data And RAG Engineer Perspective

The canonical data layer must be durable, inspectable, local, and portable
between machines. Documents and events need immutable ledgers for provenance,
while query paths need fast indexes. Dense vector search alone is insufficient
because exact names, command output, file paths, citations, and error messages
often matter more than semantic similarity.

Decision: Postgres + pgvector is canonical storage for normal work and personal
profiles. Each profile has its own database. Retrieval is hybrid BM25 + dense
vector search. Raw assets and parsed representations live on disk under the
profile root. Document, memory, task, and agent records live in Postgres and are
mirrored to JSONL ledgers for auditability and offline troubleshooting.

### Agent Orchestration Engineer Perspective

The platform needs to coordinate local coding agents, research agents, and
document-processing agents without binding itself to one harness. `pi`,
OpenCode, and Hermes are harnesses. They are not the orchestration system. tmux
is the neutral substrate that also works with mobile terminal clients.

Decision: Zsper Orchestrator is a first-party local task/run service. It owns
task state, run state, event logs, artifacts, summaries, and harness adapters.
OpenClaw and Mission Control are reference implementations or optional adapters,
not core dependencies.

### Security And Privacy Engineer Perspective

The primary risk is accidental data bleed between work and personal installs, or
unexpected calls to hosted services during local workflows. The second risk is
remote exposure. The third risk is a confused agent writing into the wrong
profile.

Decision: All flows enforce profile scoping at the filesystem, database,
secret, config, and runtime levels. Personal remote access may use Tailscale
Serve only. Tailscale Funnel is never allowed. Work remote access stays disabled
unless a local policy file explicitly enables it. Core flows do not call hosted
search, hosted model, hosted extraction, Notion, or Linear.

### Frontend Product Engineer Perspective

The UI should feel like an operational local workspace, not a landing page. It
needs dense but readable navigation, fast switching between records, citation
inspection, and agent-run timelines. The browser app is the product surface for
brain work; terminal agents are the automation surface.

Decision: `zsper-brain` is a Next.js app backed by local APIs. It uses a
work-focused layout with persistent navigation, resizable panes, compact record
tables, inspector panels, and citation previews. It avoids marketing-style hero
sections and decorative cards.

### DevOps Engineer Perspective

Work and personal installs need reproducible local startup without requiring a
Kubernetes or cloud stack. Docker Compose is allowed and sufficient for local
services. Model serving remains outside this compose stack because it is
hardware-sensitive and already owned by `llm-server`.

Decision: `zsper brain up` renders profile-specific Docker Compose and env
files, then starts Postgres + pgvector, Redis, SearXNG, Honcho, local API, and
Next.js web. `zsper code start` delegates to the `llm-server` deploy contract.

### Test Engineer Perspective

The most important tests prove isolation and absence of unexpected hosted calls.
RAG tests must verify parsing, chunking, citation anchors, BM25 retrieval, dense
retrieval, answer citation wiring, and provenance. Orchestration tests must
verify tasks, tmux launch commands, event streaming, artifacts, and resume.

Decision: Test design starts with profile isolation fixtures. The core suite
creates at least one work profile and one personal profile, runs the same flows,
and asserts no shared state at every boundary.

## Project Boundary

### Repository Responsibilities

`~/source/llm-server`:

- Installs and upgrades model-serving engines.
- Starts and stops oMLX serving profiles.
- Owns model artifacts, model-server command rendering, local-server state,
  direct API health checks, and model smoke checks.
- Publishes an OpenAI-compatible endpoint for Zsper.
- Keeps benchmark and production serving evidence separate from product UX.

`~/source/zsper`:

- Owns all user-facing product commands.
- Owns work, personal, and air profile initialization and isolation.
- Generates client configs for Zed, OpenCode, Pi/little-coder, and optional
  Hermes launcher profiles.
- Owns `zsper-brain` web app, local APIs, data model, RAG, memories, notes,
  tasks, and research inbox.
- Owns `Zsper Orchestrator`, task/run records, harness adapters, tmux launch,
  event logs, artifacts, summaries, and mobile resume.
- Owns project documentation, specs, plans, tests, and release packaging for the
  product platform.

### Dependency Direction

Zsper may depend on `llm-server` as a command or endpoint provider.
`llm-server` must not depend on `zsper`.

Allowed dependency forms:

- Environment variable pointing to the model server command:
  `ZSPER_LLM_SERVER_DIR=/Users/michaelasper/source/llm-server`.
- Configured command templates such as:
  `mise -C "$ZSPER_LLM_SERVER_DIR" run prod-start-zsper`.
- HTTP calls to `http://127.0.0.1:9127/v1/models` and
  `http://127.0.0.1:9127/v1/chat/completions`.
- A future small deploy contract file emitted by `llm-server`, for example
  `reports/local-server/zsper-endpoint.json`.

Disallowed dependency forms:

- Importing benchmark internals from `llm-server` into Zsper product code.
- Storing profile-specific product data in `llm-server`.
- Generating Zed/OpenCode/Pi configs from `llm-server`.
- Adding Brain, RAG, memory, or task orchestration code to `llm-server`.

## Product Goals

1. Provide a local AI workspace that can be used every day for coding, research,
   notes, tasks, document Q&A, and agent orchestration.
2. Keep work and personal data fully isolated using identical deployment shape.
3. Make local model serving feel like a stable utility rather than a benchmark
   experiment.
4. Make citations and provenance first-class for every answer involving
   documents, web captures, notes, memories, or prior agent runs.
5. Support mobile/remote attachment through tmux-compatible substrates without
   changing the core architecture.
6. Support offline use with local notes, tasks, file-only retrieval, and a
   smaller local code model.
7. Leave room for future plugins without allowing plugins to become core
   requirements.

## Product Non-Goals

1. Zsper is not a SaaS app.
2. Zsper is not an Open WebUI skin.
3. Zsper is not a benchmark harness.
4. Zsper is not a thin wrapper around Notion, Linear, hosted search, or hosted
   model APIs.
5. Zsper is not a general-purpose cloud agent platform.
6. Zsper does not attempt to own low-level model serving while `llm-server`
   remains available.
7. Zsper does not expose personal data through public tunnels.

## Operating Modes

### Work Mode

Purpose: professional coding, notes, docs, tasks, research, and agent runs.

Defaults:

```yaml
mode: work
remote_access_policy: disabled
network_policy: local-first
model_profile: zsper-qwen35-oq6-fp16-mtp-omlx-128k
long_context_fallback: null
storage_backend: postgres-pgvector
embedding_profile: local-bge-small-en-v1.5
```

Design decisions:

- Work data root is independent from personal data root.
- Work secrets are independent from personal secrets.
- Remote access is disabled unless an explicit local policy file enables a
  private tailnet exposure.
- Work profile can use SearXNG if configured locally, but hosted search APIs are
  not core.

### Personal Mode

Purpose: personal chat, research, documents, notes, memories, tasks, and agent
experiments.

Defaults:

```yaml
mode: personal
remote_access_policy: tailscale-serve-only
network_policy: local-first
model_profile: zsper-qwen35-oq6-fp16-mtp-omlx-128k
long_context_fallback: zsper-qwen35-oq6-omlx-256k
storage_backend: postgres-pgvector
embedding_profile: local-bge-small-en-v1.5
```

Design decisions:

- Personal can expose UI/API through Tailscale Serve.
- Personal never uses Tailscale Funnel.
- Personal may retain richer long-term memory than work if the user chooses,
  but it still uses the same record schema.
- Personal long-context fallback is available for heavy document or memory
  sessions.

### Air Mode

Purpose: lower-compute local coding, portable work, and local notes/tasks.

Defaults:

```yaml
mode: air
remote_access_policy: disabled
network_policy: local-first
model_profile: zsper-air-gemma4-12b-it-6bit-128k
long_context_fallback: null
storage_backend: sqlite-or-postgres-local
embedding_profile: local-small-embedding
```

Design decisions:

- Air uses the smaller local code model and a SQLite-compatible storage path by
  default.
- The default code-only model is Gemma 4 12B 6-bit.
- Qwen 9B is not added by default until artifact verification and quality checks
  prove it is worth including.

### Offline State

Purpose: degraded operation when the current profile must avoid hosted or
network-dependent work.

Defaults:

```yaml
network_policy: offline
```

Design decisions:

- Offline state can be used by work, personal, and air profiles.
- Offline state disables web capture, SearXNG querying, hosted calls, plugin
  network access, and model artifact downloads.
- Offline state keeps file-only retrieval and local notes/tasks available.

## Profile Isolation

Profiles are the root of all isolation. Every command resolves a profile before
performing work.

### Profile Root Layout

Each profile root uses the same layout:

```text
<profile-root>/
  profile.json
  secrets/
  runtime/
    code/
    brain/
    agents/
  models/
    huggingface/
    embeddings/
  code/
    zed/
    opencode/
    pi/
    hermes/
  brain/
    docker-compose.yml
    .env
    schema.sql
    assets/
    parsed/
    ledgers/
    notes/
    tasks/
    memory/
    documents/
    citations/
  agent-runs/
    runs.jsonl
    events/
    artifacts/
    summaries/
  logs/
```

Design decisions:

- `profile.json` is the source of truth for profile metadata.
- `secrets/` is profile-scoped and excluded from sync by default.
- `runtime/` is disposable state. Deleting it should not delete canonical user
  data.
- `brain/ledgers/` contains append-only JSONL mirrors for audit and recovery.
- `agent-runs/` stores independent histories per profile.
- Generated client configs are profile-local. Global installation is a separate
  explicit command with a diff and backup.

### Profile Record

```typescript
type Profile = {
  schema_version: 1;
  name: string;
  mode: "work" | "personal" | "air";
  root: string;
  model_profile: string;
  long_context_fallback: string | null;
  embedding_profile: string;
  storage_backend: "postgres-pgvector" | "sqlite-local";
  remote_access_policy: "disabled" | "tailscale-serve-only";
  network_policy: "local-first" | "offline";
  database_name: string;
  created_at: string;
  updated_at: string;
};
```

Profile invariants:

- `root` must be absolute after initialization.
- `database_name` must be unique across work and personal installs.
- `mode=work` implies `remote_access_policy=disabled` by default.
- `mode=personal` may use `tailscale-serve-only`.
- `mode=air` implies `remote_access_policy=disabled`.
- `network_policy=offline` is valid for every mode.

## Public CLI

The CLI name is `zsper`.

### Profile Commands

```bash
zsper profile init --mode work|personal|air --root <path>
zsper profile list
zsper profile show --profile <name-or-root>
zsper profile doctor --profile <name-or-root>
```

Decisions:

- `profile init` creates directories, writes `profile.json`, and validates that
  the target root is not already used by another profile.
- `profile list` reads a local registry, not global shell history.
- `profile doctor` verifies directory permissions, database reachability,
  endpoint config, secrets presence, remote-access policy, and forbidden hosted
  integrations.

### Code Commands

```bash
zsper code start --profile <name-or-root>
zsper code stop --profile <name-or-root>
zsper code status --profile <name-or-root>
zsper code smoke --profile <name-or-root>
zsper code install-zed --profile <name-or-root>
zsper code install-opencode --profile <name-or-root>
zsper code install-pi --profile <name-or-root>
```

Decisions:

- `code start|stop|status|smoke` delegates to the `llm-server` deploy contract.
- `code install-*` writes profile-local adapter configs first.
- A separate `--global` flag can patch real user configs later, but the default
  is profile-local generation.
- The generated configs point to the profile-selected model endpoint.

### Brain Commands

```bash
zsper brain up --profile <name-or-root>
zsper brain down --profile <name-or-root>
zsper brain status --profile <name-or-root>
zsper brain ingest <path-or-url> --profile <name-or-root>
zsper brain search <query> --profile <name-or-root>
zsper brain answer <query> --profile <name-or-root>
```

Decisions:

- `brain up` starts only brain services, not model serving.
- `brain ingest` uses Docling for supported local documents, local text parsing
  for Markdown/plain text/source files, and local web capture for URLs when
  network policy allows it.
- `brain answer` always returns citations when it uses retrieved context.

### Agent Commands

```bash
zsper agent run --harness pi|opencode|hermes --task <id> --profile <name-or-root>
zsper agent attach --run <id> --profile <name-or-root>
zsper agent status --run <id> --profile <name-or-root>
zsper agent cancel --run <id> --profile <name-or-root>
```

Decisions:

- `agent run` creates an `AgentRun` before launching tmux.
- Harnesses are adapters behind the Zsper Orchestrator.
- Run events are recorded even when the harness output is messy.
- Attach uses tmux session identity and remains neutral to Moshi, SSH, Litter,
  Attach, AgentShell, or other terminal clients.

## Zsper Code

### Purpose

`zsper-code` gives editors and coding agents a stable local model interface.
It is not the model server itself.

### Model Endpoint Record

```typescript
type ModelEndpoint = {
  provider_id: string;
  base_url: string;
  model_id: string;
  context_window: number;
  output_limit: number;
  tool_support: boolean;
  health_path: "/models";
};
```

Primary endpoint:

```yaml
provider_id: zsper-code
base_url: http://127.0.0.1:9127/v1
model_id: zsper-qwen35-oq6-fp16-mtp-omlx-128k
context_window: 131072
output_limit: 4096
tool_support: true
```

Personal fallback:

```yaml
provider_id: zsper-code-long
base_url: http://127.0.0.1:9127/v1
model_id: zsper-qwen35-oq6-omlx-256k
context_window: 262144
output_limit: 4096
tool_support: true
```

Air endpoint:

```yaml
provider_id: zsper-air-code
base_url: http://127.0.0.1:9127/v1
model_id: zsper-air-gemma4-12b-it-6bit-128k
context_window: 131072
output_limit: 4096
tool_support: true
```

### Zed Adapter

Generated files:

```text
<profile-root>/code/zed/settings.json
<profile-root>/code/zed/context_servers.json
```

Design decisions:

- Zed uses an OpenAI-compatible provider config.
- Zed context server points back to `zsper brain context-server`.
- Generated files are profile-local until explicitly installed globally.
- The Zed model id is the Zsper model profile id, not the raw Hugging Face model
  reference.

### OpenCode Adapter

Generated file:

```text
<profile-root>/code/opencode/opencode.json
```

Design decisions:

- Provider uses `@ai-sdk/openai-compatible`.
- Agent name is `zsper-code`.
- The provider API key is a local sentinel value because the endpoint is local.
- Existing global OpenCode config is patched only by an explicit install command
  that writes a backup and redacted diff.

### Pi And little-coder Adapter

Generated files:

```text
<profile-root>/code/pi/pi-provider.yml
<profile-root>/code/pi/AGENTS.md
<profile-root>/code/pi/little-coder.md
```

Design decisions:

- Pi is a minimal extensible harness for local coding flows.
- little-coder conventions are packaged with Pi for weak/local model behavior:
  short loops, explicit file reads, small diffs, deterministic checks, and
  conservative task expansion.
- Pi configs should work without global shell mutation.

### Hermes Launcher Profile

Design decisions:

- Hermes is optional and launch-oriented.
- Hermes is not the core orchestrator.
- Hermes profile generation is allowed as a client adapter under
  `<profile-root>/code/hermes/`.

## Zsper Brain

### Purpose

`zsper-brain` is the user's local shell for chat, research, document RAG, notes,
tasks, memories, and agent orchestration.

### Service Topology

```text
Next.js Web Shell
  -> Brain API
      -> Postgres + pgvector
      -> Redis
      -> Local file store
      -> SearXNG
      -> Docling parser
      -> Embedding worker
      -> Honcho sidecar
      -> Zsper Orchestrator
      -> OpenAI-compatible local model endpoint
```

Design decisions:

- Brain services run under Docker Compose for work/personal installs.
- Model serving does not run inside Brain Compose.
- Honcho is a memory sidecar, not canonical storage.
- Zsper retains canonical event/document/task ledgers.
- SearXNG is local/self-hosted metasearch.
- Hosted search APIs are not core.
- Docling is preferred for local and air-gapped document parsing.

### Web Shell

Primary views:

- Chat
- Research Inbox
- Documents
- Citations
- Notes
- Tasks
- Memories
- Agent Runs
- Settings

Layout decisions:

- Persistent left navigation.
- Main work area with view-specific table/list/thread.
- Right inspector for metadata, citations, run events, or document chunks.
- Dense operational UI, not a marketing page.
- Cards are reserved for repeated items and dialogs, not whole page sections.
- The first screen after startup is the actual workspace.

### Brain API

API groups:

```text
/api/chat
/api/research
/api/documents
/api/citations
/api/notes
/api/tasks
/api/memories
/api/agents
/api/settings
/api/search
/api/health
```

Design decisions:

- API responses include profile id and record ids for audit.
- Mutating endpoints append events to the canonical ledger.
- RAG answer endpoints return citation objects, not only formatted text.
- Agent endpoints expose run state and event streams.

### Storage

Canonical database for work/personal:

- Postgres
- pgvector

Profile-specific database names:

```text
zsper_work
zsper_personal
zsper_air
```

Air defaults to a SQLite-compatible local storage path. Offline state may use
SQLite-compatible local stores for degraded operation even when the normal
profile backend is Postgres. SQLite mode must preserve the same logical record
schema.

### Document Pipeline

Pipeline:

```text
Raw source
  -> Asset capture
  -> Parser selection
  -> Parsed representation
  -> Chunking
  -> Citation anchor generation
  -> Embedding
  -> BM25 indexing
  -> Dense vector indexing
  -> Retrieval-ready document record
```

Parser decisions:

- Markdown, text, JSON, YAML, and source files can use local text parsing.
- PDFs, Office files, and complex HTML use Docling.
- Webpages are captured locally when network policy allows.
- Offline state rejects URL ingestion and accepts file paths only.

Chunking decisions:

- Chunks preserve citation anchors.
- Chunks store token estimate and byte offsets when available.
- Chunk ids are deterministic within a document version.
- Re-ingesting an unchanged file should not duplicate canonical records.

Citation decisions:

- Citation anchors are first-class records.
- Answers must cite the exact chunks used.
- The UI lets users inspect source text around a citation.
- Citation confidence is separate from answer confidence.

### Retrieval

Hybrid retrieval layers:

- BM25 for exact terms, file paths, commands, names, identifiers, and error
  messages.
- Dense vectors for semantic similarity.
- Optional reranking by local model when latency allows.

Decision:

- Hybrid retrieval is the default. Dense-only retrieval is not acceptable for
  coding, notes, or citations.

### Research Inbox

Purpose:

- Capture local search results.
- Group sources by topic.
- Preserve snippets, capture timestamp, URL, query, and extraction status.
- Feed selected sources into document ingestion.

Design decisions:

- SearXNG is the default discovery service.
- Search results are not automatically trusted.
- Research records are distinct from document records until ingested.
- Offline state disables external research and keeps local-only saved research.

### Notes

Purpose:

- Store lightweight local notes with optional backlinks, citations, tags, and
  task links.

Design decisions:

- Notes are canonical records, not only Markdown files.
- Notes can be exported as Markdown.
- Notes can be embedded and retrieved.
- Notes are profile-local.

### Tasks

Purpose:

- Track user tasks and agent-executable tasks.

Design decisions:

- Tasks are first-party records.
- Tasks can be linked to documents, notes, memories, and agent runs.
- Tasks can be launched through harness adapters.
- Task state transitions are event-sourced.

### Memories

Purpose:

- Preserve useful summaries, preferences, project facts, decisions, and
  interaction context.

Design decisions:

- Zsper owns canonical `MemoryEvent` records.
- Honcho can derive and retrieve memory, but it does not replace the canonical
  ledger.
- Every memory has source, participants, session, summary, confidence, and
  provenance.
- Memories can be disabled per profile.
- Work memories should be conservative and project-scoped by default.

## Data Model

### Document

```typescript
type Document = {
  id: string;
  profile_id: string;
  source_type: "file" | "url" | "repo" | "note" | "agent_artifact";
  raw_asset_path: string;
  parsed_representation_path: string;
  title: string;
  metadata: Record<string, unknown>;
  content_hash: string;
  parser: "text" | "docling" | "web-capture" | "repo";
  created_at: string;
  updated_at: string;
};
```

### DocumentChunk

```typescript
type DocumentChunk = {
  id: string;
  document_id: string;
  chunk_index: number;
  text: string;
  citation_anchor_id: string;
  token_estimate: number;
  byte_start: number | null;
  byte_end: number | null;
  embedding_model: string | null;
  embedding_vector_id: string | null;
};
```

### CitationAnchor

```typescript
type CitationAnchor = {
  id: string;
  document_id: string;
  chunk_id: string;
  label: string;
  source_path_or_url: string;
  display_range: string | null;
};
```

### MemoryEvent

```typescript
type MemoryEvent = {
  id: string;
  profile_id: string;
  source: "chat" | "note" | "task" | "agent_run" | "manual" | "document";
  participants: string[];
  session: string;
  summary: string;
  confidence: number;
  provenance: Record<string, unknown>;
  created_at: string;
};
```

### Task

```typescript
type Task = {
  id: string;
  profile_id: string;
  title: string;
  description: string;
  status: "inbox" | "ready" | "running" | "blocked" | "done" | "canceled";
  priority: "low" | "normal" | "high";
  links: Record<string, string[]>;
  created_at: string;
  updated_at: string;
};
```

### AgentRun

```typescript
type AgentRun = {
  id: string;
  profile_id: string;
  task_id: string;
  harness: "pi" | "opencode" | "hermes";
  tmux_session: string;
  model_endpoint: ModelEndpoint;
  event_log_path: string;
  artifacts_path: string;
  summary_path: string | null;
  final_status: "planned" | "running" | "succeeded" | "failed" | "blocked" | "canceled";
  created_at: string;
  updated_at: string;
};
```

### AgentRunEvent

```typescript
type AgentRunEvent = {
  id: string;
  run_id: string;
  sequence: number;
  event_type:
    | "started"
    | "stdout"
    | "stderr"
    | "tool_call"
    | "tool_result"
    | "artifact"
    | "summary"
    | "status_change"
    | "completed";
  payload: Record<string, unknown>;
  created_at: string;
};
```

## Zsper Orchestrator

### Purpose

Zsper Orchestrator coordinates task execution across local agent harnesses while
keeping run history, artifacts, event logs, and summaries canonical in Zsper.

### Orchestration Pattern

The core pattern is hierarchical plus tool-mediated:

- User creates or selects a task.
- Orchestrator validates profile, task, harness, and model endpoint.
- Orchestrator creates an `AgentRun`.
- Harness adapter renders a tmux launch command.
- Agent runs in tmux.
- Event collector records stdout, stderr, tool calls, artifacts, summaries, and
  status transitions.
- UI and CLI read run state from Zsper, not from a harness-specific history.

### Harness Adapters

Pi adapter:

- Best for minimal local code loops and weak/local model workflows.
- Uses Pi provider config generated by `zsper code install-pi`.
- Applies little-coder conventions.

OpenCode adapter:

- Best for local OpenAI-compatible coding workflows.
- Uses profile-local OpenCode config.
- Emits events when OpenCode output can be parsed.

Hermes adapter:

- Optional launcher profile.
- Not a core orchestrator.
- Useful for experiments where Hermes is the preferred shell.

### Agent Communication

Communication patterns:

- Direct user-to-orchestrator commands through CLI or web UI.
- Tool-mediated agent communication through shared task/run/document records.
- Event logs for replay and diagnosis.
- Summaries for compact future context.

Decision:

- Agents do not directly mutate other agents' state. They write events,
  artifacts, and task updates through the orchestrator API.

### Run State Machine

Allowed transitions:

```text
planned -> running
running -> succeeded
running -> failed
running -> blocked
running -> canceled
blocked -> running
failed -> running
```

Disallowed transitions:

- `succeeded -> running`
- `canceled -> running`
- `planned -> succeeded` without a started event

### Mobile Attach

Design decisions:

- tmux is the neutral substrate.
- Moshi, SSH clients, Litter, Attach, and AgentShell are attachment layers.
- Zsper does not require a specific mobile client.
- Run records include tmux session names so attach flows are reproducible.

## Security And Privacy

### Core Rules

1. Work and personal profiles do not share state.
2. Core flows do not call hosted model APIs.
3. Core flows do not call hosted search APIs.
4. Core flows do not call hosted extraction APIs.
5. Notion and Linear are plugins only.
6. Personal remote access may use Tailscale Serve only.
7. Tailscale Funnel is forbidden.
8. Work remote access is disabled unless an explicit local policy enables it.
9. Secrets are profile-local and never written into diffs or logs.
10. Generated global config patches must write backups and redacted diffs.

### Secret Handling

Profile secret paths:

```text
<profile-root>/secrets/
  brain.env
  model.env
  plugins/
```

Decisions:

- Local-only sentinel API keys are allowed for local OpenAI-compatible
  endpoints.
- Real tokens are stored under `secrets/`.
- Secret values are not copied into JSONL ledgers.
- Diffs redact keys named `apiKey`, `api_key`, `token`, `authorization`,
  `password`, and `secret`.

### Network Policy

`local-first`:

- Allows localhost services.
- Allows SearXNG if locally configured.
- Allows explicit user-triggered web capture.
- Blocks hosted integrations unless plugin policy enables them.

`offline`:

- Allows localhost services.
- Allows local file reads under user-selected paths.
- Blocks URLs, SearXNG, hosted integrations, and model artifact downloads.

## Observability

### Logs

Profile log paths:

```text
<profile-root>/logs/brain-api.log
<profile-root>/logs/brain-web.log
<profile-root>/logs/orchestrator.log
<profile-root>/runtime/code/logs/
```

### Event Ledgers

Append-only ledgers:

```text
<profile-root>/brain/ledgers/documents.jsonl
<profile-root>/brain/ledgers/memory-events.jsonl
<profile-root>/brain/ledgers/tasks.jsonl
<profile-root>/agent-runs/runs.jsonl
<profile-root>/agent-runs/events/<run-id>.jsonl
```

Decisions:

- Ledgers are for audit, replay, debugging, and offline recovery.
- Postgres remains canonical for online work/personal installs.
- Ledgers should be readable without running services.

### Health Checks

Health surfaces:

- `zsper profile doctor`
- `zsper code status`
- `zsper code smoke`
- `zsper brain status`
- `zsper agent status`
- `/api/health`

Health checks verify:

- Profile exists and matches schema.
- Runtime directories are writable.
- Database is reachable.
- Model endpoint responds to `/models`.
- Brain API responds.
- Web UI responds.
- SearXNG status matches network policy.
- No forbidden hosted integrations are configured in core flows.

## Testing Strategy

### Isolation Tests

Create work and personal profiles. Assert:

- Different roots.
- Different Postgres database names.
- Different secret directories.
- Different vector tables or schema namespaces.
- Different generated client configs.
- Different agent run histories.
- Different memory ledgers.
- No cross-profile search results.

### Model Serving Tests

For each model profile:

- Render deployment command through `llm-server`.
- Start endpoint.
- Check `/v1/models`.
- Run smoke chat completion.
- Stop endpoint.
- Assert profile-specific runtime state and logs.

Zsper product tests should mock this contract except for integration gates.

### Adapter Config Tests

Generated Zed config:

- Points to `http://127.0.0.1:9127/v1`.
- Uses Zsper model id.
- Includes local context server command.

Generated OpenCode config:

- Uses OpenAI-compatible provider.
- Uses local base URL.
- Uses profile model id and context limits.

Generated Pi package:

- Includes provider YAML.
- Includes little-coder conventions.

### RAG Tests

Ingest:

- PDF.
- Markdown.
- Webpage capture.
- Source repo docs.

Assert:

- Raw asset exists.
- Parsed representation exists.
- Chunks exist.
- Citation anchors exist.
- Embeddings exist.
- BM25 results include exact matches.
- Dense results include semantic matches.
- Answers include citations.

### Orchestration Tests

Flow:

- Create task.
- Launch Pi run in tmux.
- Stream events.
- Attach artifact.
- Complete task.
- Resume from mobile-equivalent tmux attach command.

Assert:

- Run record exists before launch.
- Event log sequences are monotonic.
- Tool events are captured.
- Artifacts are linked.
- Final status is correct.

### Offline Tests

With network disabled:

- Initialize a profile in offline state.
- Start code endpoint using local model artifact.
- Create notes.
- Create tasks.
- Ingest local Markdown.
- Run file-only retrieval.

Assert:

- URL ingestion fails with a clear policy error.
- SearXNG is not called.
- Hosted model/search/extraction calls are not made.

### Security Tests

Assert:

- Core flows do not reference Notion or Linear.
- Core flows do not require hosted search API keys.
- Core flows do not require hosted model API keys.
- Personal remote policy rejects Funnel.
- Work remote policy defaults to disabled.
- Global config patches redact secrets in diffs.

## Suggested Project Structure

```text
~/source/zsper/
  README.md
  pyproject.toml
  package.json
  docs/
    zsper-local-ai-platform-ultimate-spec.md
    architecture/
    runbooks/
    superpowers/
      plans/
  src/
    zsper/
      __init__.py
      cli.py
      profiles/
      code/
      brain/
      rag/
      memory/
      orchestrator/
      security/
      config/
      utils/
  apps/
    brain-web/
  services/
    brain-api/
  compose/
  tests/
    unit/
    integration/
    fixtures/
```

Design decisions:

- Python owns CLI, profile management, config generation, RAG workers, and
  orchestrator service.
- Next.js owns the brain web shell.
- Brain API can begin as Python FastAPI to keep profile, RAG, and orchestrator
  code in one language.
- Shared TypeScript types for the web app are generated from API schemas later.

## Implementation Phases

### Phase 1: Documentation And Project Baseline

Deliverables:

- This ultimate spec.
- README with project purpose and repo boundary.
- Basic Python project scaffold.
- Test runner.
- Empty CLI entry point.

Success criteria:

- New contributor can explain the repo boundary.
- No product code exists in `llm-server`.
- `zsper` tests can run independently.

### Phase 2: Profiles And Code Adapters

Deliverables:

- Profile init/list/show/doctor.
- Profile-local Zed config generation.
- Profile-local OpenCode config generation.
- Profile-local Pi/little-coder package generation.
- Code endpoint health and smoke checks through external model-server contract.

Success criteria:

- Work and personal profile isolation tests pass.
- Generated configs point to the right endpoint.
- No global configs are patched by default.

### Phase 3: Brain Storage And Compose

Deliverables:

- Profile-specific Docker Compose render.
- Postgres + pgvector schema.
- Redis.
- SearXNG.
- Honcho sidecar.
- Brain API health endpoint.
- Brain web shell starter workspace.

Success criteria:

- `zsper brain up` starts local services.
- Work and personal databases are distinct.
- `zsper brain status` reports health.

### Phase 4: Documents And RAG

Deliverables:

- Document ingestion.
- Docling parser integration.
- Chunking.
- Citation anchors.
- Local embeddings.
- BM25 index.
- Dense vector index.
- Hybrid search.
- Citation-grounded answer flow.

Success criteria:

- Markdown, PDF, webpage capture, and repo docs are ingestible.
- Search returns exact and semantic results.
- Answers include inspectable citations.

### Phase 5: Notes, Tasks, Memories

Deliverables:

- Notes records.
- Tasks records.
- MemoryEvent records.
- Honcho sidecar integration.
- UI views for notes, tasks, and memories.

Success criteria:

- Notes/tasks/memories are profile-local.
- Memory provenance is inspectable.
- Honcho can be disabled without losing canonical Zsper records.

### Phase 6: Orchestrator And Agent Runs

Deliverables:

- First-party task/run service.
- Pi adapter.
- OpenCode adapter.
- Optional Hermes adapter.
- tmux launch.
- Event collector.
- Artifact capture.
- Run summaries.
- Agent Runs UI.

Success criteria:

- Create task, launch agent, stream events, attach artifact, finish run.
- Resume via tmux-compatible mobile client.
- Run history remains profile-local.

### Phase 7: Offline And Security Gates

Deliverables:

- Offline policy enforcement.
- Offline file-only retrieval.
- No-network test harness.
- Hosted-call detection tests.
- Remote access policy checks.

Success criteria:

- Work, personal, and air profiles work in offline state without network.
- Forbidden hosted calls fail tests.
- Personal Serve policy is allowed.
- Funnel is rejected.

## Design Decision Log

1. `llm-server` owns oMLX deployment; `zsper` owns product platform.
2. Model-serving contract is OpenAI-compatible HTTP plus health/smoke metadata.
3. Profiles are the unit of isolation.
4. Work and personal share code, not state.
5. Personal may use Tailscale Serve only.
6. Work remote access defaults to disabled.
7. Air defaults to Gemma 4 12B 6-bit code-only profile.
8. Qwen 9B is excluded from air default until verified.
9. Postgres + pgvector is canonical for work/personal.
10. JSONL ledgers mirror canonical events for audit and recovery.
11. Honcho is a sidecar, not canonical memory storage.
12. Docling is the preferred local document parser.
13. Retrieval is hybrid BM25 + dense vector.
14. SearXNG is local metasearch.
15. Hosted search APIs are not core.
16. Notion and Linear are future plugins only.
17. OpenClaw and Mission Control are references or adapters, not core.
18. Zsper Orchestrator owns task/run state.
19. tmux is the neutral agent substrate.
20. Moshi and other mobile tools attach to tmux; they do not shape core state.
21. Zed, OpenCode, Pi, and Hermes are generated client adapters.
22. Generated adapter configs are profile-local by default.
23. Global config patching requires explicit command, backup, and redacted diff.
24. The web shell is the main Brain UX.
25. The first Brain UI is a workspace, not a landing page.
26. Core flows must not call hosted models, hosted search, hosted extraction,
    Notion, or Linear.

## Future Plugin Policy

Plugins can add:

- Notion sync.
- Linear sync.
- Hosted search.
- Hosted model fallback.
- Hosted extraction.
- Alternative agent harnesses.
- Alternative memory providers.

Plugin requirements:

- Must be disabled by default.
- Must declare network behavior.
- Must declare secret requirements.
- Must declare profile scope.
- Must be covered by security tests.
- Must not become a core dependency.

## Open Questions With Default Decisions

These questions are not blockers because this spec chooses a default.

1. Should Brain API be Python or TypeScript?
   Default decision: Python FastAPI, because profile/RAG/orchestrator code is
   Python-first and easier to test locally.

2. Should offline state use Postgres or SQLite first?
   Default decision: support local Postgres when available, but allow SQLite for
   file-only offline iteration.

3. Should global editor config patching be automatic?
   Default decision: no. Generate profile-local configs by default. Patch global
   configs only with explicit commands.

4. Should Honcho own memory?
   Default decision: no. Honcho is a sidecar. Zsper owns canonical events.

5. Should the orchestrator adopt OpenClaw?
   Default decision: no. Build Zsper Orchestrator. Keep OpenClaw as reference or
   adapter.

6. Should remote access be configured during profile init?
   Default decision: no. Profile init records policy; explicit brain remote
   commands configure Serve later.

## Acceptance Criteria For The Whole Project

Zsper is ready for first daily use when:

- Work and personal profiles initialize cleanly.
- `zsper code start|status|smoke|stop` works through `llm-server`.
- Zed, OpenCode, and Pi configs generate under each profile.
- Brain Compose starts for a profile.
- Chat can use the local model endpoint.
- Markdown and PDF ingestion produce chunks and citation anchors.
- Hybrid search works.
- Citation-grounded answers work.
- Notes, tasks, and memory events can be created and searched.
- An agent task can launch through tmux, record events, and attach artifacts.
- Work and personal isolation tests prove no shared state.
- Work, personal, and air profiles work with local files and no network when
  offline state is active.
- Security tests prove forbidden hosted integrations are not called in core
  flows.
