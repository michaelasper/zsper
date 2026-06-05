# Zsper

<p align="center">
  <b>A local AI workspace with profile isolation, Brain storage, RAG, and agent-ready workflows.</b>
</p>

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"
zsper profile use work
```

Zsper keeps local AI work organised by profile. Each profile owns its config,
Brain data, retrieval indexes, ledgers, runtime files, and generated adapter
settings. Model serving stays outside this repository and is reached through
local OpenAI-compatible endpoints.

## Why Zsper

| Capability | What it gives you |
| --- | --- |
| Profile isolation | Keep work, personal, and portable contexts separate by default. |
| Local Brain storage | Store documents, chunks, citations, notes, tasks, and runtime metadata under the selected profile. |
| Hybrid BM25 + dense retrieval | Balance exact terms with semantic recall. |
| Citation objects | `brain answer` returns citation objects that can be inspected later. |
| Local model contracts | Use `llm-server` or another local OpenAI-compatible service without importing model-server internals. |
| Append-only ledgers | Mirror mutating Brain records to profile-local JSONL for audit and recovery. |

## Quick Start

```bash
# Install the CLI into your home directory.
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash

# Create a profile. Installation does not choose one for you.
zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"

# Set the default profile for commands that omit --profile.
zsper profile use work

# Check the profile layout and policy.
zsper profile doctor

# Ingest and search local content.
zsper brain ingest ~/notes/project.md
zsper brain search project
```

## Profile Modes

Profiles define the trust and runtime boundary for a workflow.

| Mode | Use it for | Storage | Network posture |
| --- | --- | --- | --- |
| `work` | Professional projects and private work data | Postgres + pgvector | Local-first, remote access disabled |
| `personal` | Personal projects and private personal data | Postgres + pgvector | Local-first, Tailscale Serve allowed |
| `air` | Portable or lower-compute contexts | Profile-local SQLite path | Local-first, remote access disabled |

The mode is not the profile name. Choose names that match the machine or
workflow, such as `work`, `personal`, `portable`, `field`, or `travel`.
Offline is a network-policy state, not a mode; any profile can start offline
with `--network-policy offline`.

Read [Profile Modes](docs/architecture/profile-modes.md) for the design
model and the exact defaults.

## Install

The installer creates a managed checkout, virtual environment, wrapper command,
and home-scoped configuration. It does not create a profile or set a default.

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
```

After install:

```bash
zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"
zsper profile use work
zsper profile doctor
```

For a portable profile:

```bash
zsper profile init \
  --mode air \
  --name portable \
  --root "$HOME/.local/share/zsper/profiles/portable"
zsper profile use portable
```

## Develop From Source

```bash
git clone https://github.com/michaelasper/zsper.git
cd zsper
python -m pip install -e ".[api,database,rag]"
python -m zsper --help
```

To prepare a portable profile from a checkout:

```bash
./setup.sh --air --name portable
```

`./setup.sh --air` is a source-tree convenience wrapper. It prepares a portable
profile, creates a readiness note, ingests it, and verifies local search without
hosted model, search, or extraction calls.

## Repository Boundary

Zsper is split from `llm-server`:

| Repository | Owns |
| --- | --- |
| `/Users/michaelasper/source/llm-server` | owns model deployment and oMLX serving |
| `/Users/michaelasper/source/zsper` | owns profiles, CLI, configs, Brain, RAG, orchestrator, docs, and tests |

Zsper may use `llm-server` only through stable external contracts such as an
environment variable, command template, deploy contract file, or local
OpenAI-compatible HTTP endpoint. It must not import benchmark internals, store
profile data in `llm-server`, generate adapters from `llm-server`, or add
Brain/RAG/memory/tasks to `llm-server`.

See [Repository Boundary](docs/architecture/repository-boundary.md) for the
allowed and disallowed dependency forms.

## Documentation

| Need | Start here |
| --- | --- |
| Understand profile modes | [Profile Modes](docs/architecture/profile-modes.md) |
| Understand the platform shape | [Platform Overview](docs/architecture/platform-overview.md) |
| Use offline state | [Offline State](docs/runbooks/offline-state.md) |
| Develop locally | [Local Development](docs/runbooks/local-development.md) |
| Run verification | [Testing](docs/runbooks/testing.md) |
| Read the full product spec | [Ultimate Spec](docs/zsper-local-ai-platform-ultimate-spec.md) |
| Follow implementation order | [Implementation DAG](docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md) |

## Current Constraints

| Constraint | Current path |
| --- | --- |
| Model download and serving live outside this repo | Prepare models through `llm-server` or another local OpenAI-compatible serving contract. |
| Rich parsing depends on local runtimes | Install the `rag` extras and keep Docling and embedding models available locally. |
| Work and personal RAG use local Postgres services | Run profile Brain services before using Postgres-backed ingest/search flows. |
| Offline state blocks hosted calls | Use `--network-policy offline` when a profile must avoid hosted model, search, extraction, and model-download calls. |

## Troubleshooting

### `zsper` is not on `PATH`

Add the wrapper directory to your shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Python is too old

Zsper requires Python 3.12 or newer.

```bash
PYTHON=python3.12 ./setup.sh --air --name portable
```

### Search returns no results

Confirm that the same profile was selected for ingest and search:

```bash
zsper profile list
zsper brain ingest --profile work ./notes.md
zsper brain search --profile work notes
```
