# Zsper

<p align="center">
  <b>Local-first AI workflows that keep profile data isolated and usable offline.</b>
</p>

```bash
./setup.sh --air
```

## TL;DR

**Problem:** local AI work often mixes personal, work, travel, model-serving,
and agent state until it is hard to trust what data moved where.

**Solution:** Zsper gives each workflow a profile boundary, a CLI surface, and
profile-local Brain storage. The current MVP is focused on getting the
`air` profile useful before the full platform DAG is complete.

| Feature | Benefit |
| --- | --- |
| Air/offline setup | Prepare an isolated travel profile with one command. |
| Profile-local Brain files | Ingest and search UTF-8 local files without hosted calls. |
| Explicit boundaries | Keep product code in `zsper` and model serving in `llm-server`. |
| Append-only ledgers | Record Brain file mutations in profile-local JSONL. |

## Quick Start

```bash
# 1. Prepare the air/offline profile.
./setup.sh --air

# 2. Use the generated profile registry in this shell if needed.
export ZSPER_PROFILE_REGISTRY="$HOME/.config/zsper/profiles.json"

# 3. Inspect the air profile.
PYTHONPATH=src python -m zsper profile show --profile air

# 4. Ingest a local UTF-8 file.
PYTHONPATH=src python -m zsper brain ingest --profile air ~/notes/flight.md

# 5. Search local profile content.
PYTHONPATH=src python -m zsper brain search --profile air offline

# 6. Verify the profile layout.
PYTHONPATH=src python -m zsper profile doctor --profile air
```

For the full air/offline workflow, use
[docs/runbooks/air-offline.md](docs/runbooks/air-offline.md).

## What Works Now

| Workflow | Example |
| --- | --- |
| Initialise profiles | `PYTHONPATH=src python -m zsper profile init --mode air-offline --root "$HOME/.local/share/zsper/profiles/air"` |
| List profiles | `PYTHONPATH=src python -m zsper profile list` |
| Inspect a profile | `PYTHONPATH=src python -m zsper profile show --profile air` |
| Doctor a profile | `PYTHONPATH=src python -m zsper profile doctor --profile air` |
| Ingest local text | `PYTHONPATH=src python -m zsper brain ingest --profile air ./notes.md` |
| Search local text | `PYTHONPATH=src python -m zsper brain search --profile air notes` |

`./setup.sh --air` creates a project virtual environment by default, writes a
small `zsper` wrapper into `.venv/bin/`, initialises or reuses the air profile,
ingests a readiness note, and verifies offline search. It does not download
models or call hosted APIs.

## Installation And Setup

### Air/offline setup

```bash
./setup.sh --air
```

Use this on the machine that will run offline. It is safe to rerun; existing air
profiles are reused.

### Source checkout

```bash
git clone https://github.com/michaelasper/zsper.git
cd zsper
PYTHONPATH=src python -m zsper --help
```

### Editable package install

```bash
python -m pip install -e .
zsper --help
```

Use the editable install when network and Python packaging dependencies are
available. The air setup script keeps the current MVP usable from source when
offline packaging is not ready.

## Repository Boundary

Zsper is split from `llm-server`:

| Repository | Owns |
| --- | --- |
| `/Users/michaelasper/source/llm-server` | owns model deployment and oMLX serving |
| `/Users/michaelasper/source/zsper` | owns profiles, CLI, configs, Brain, RAG, orchestrator, docs, and tests |

Zsper may use `llm-server` only through stable external contracts such as an
environment variable, command template, deploy contract file, or local
OpenAI-compatible HTTP endpoint. It must not import benchmark internals or move
product platform responsibilities into `llm-server`.

See [docs/architecture/repository-boundary.md](docs/architecture/repository-boundary.md)
for the allowed and disallowed dependency forms.

## Documentation

| Need | Start here |
| --- | --- |
| Product direction | [docs/zsper-local-ai-platform-ultimate-spec.md](docs/zsper-local-ai-platform-ultimate-spec.md) |
| Implementation order | [docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md](docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md) |
| Platform overview | [docs/architecture/platform-overview.md](docs/architecture/platform-overview.md) |
| Air/offline setup | [docs/runbooks/air-offline.md](docs/runbooks/air-offline.md) |
| Local development | [docs/runbooks/local-development.md](docs/runbooks/local-development.md) |
| Test commands | [docs/runbooks/testing.md](docs/runbooks/testing.md) |

## Limitations

| Limitation | Workaround | Planned direction |
| --- | --- | --- |
| Air ingest accepts UTF-8 local text only | Convert PDFs, Office files, and complex HTML before ingesting | Docling parsing in the RAG milestone |
| Search is exact local token search | Use clear local file text and direct query terms | Hybrid BM25 + dense retrieval |
| `brain answer` is still reserved | Use `brain search` for local recall | Citation-backed answers |
| Model download and serving are outside this repo | Prepare models through `llm-server` or another local serving contract | Stable local model adapter contracts |

## Troubleshooting

### `./setup.sh --air` says Python is too old

Install Python 3.12 or newer, then rerun:

```bash
PYTHON=python3.12 ./setup.sh --air
```

### The `air` profile already exists

The setup script reuses an existing registered `air` profile. To create a
separate air profile root, choose a different name and root:

```bash
./setup.sh --air --name air-laptop --root "$HOME/.local/share/zsper/profiles/air-laptop"
```

### Search returns no results

Confirm the file was ingested into the same profile registry:

```bash
PYTHONPATH=src python -m zsper profile list
PYTHONPATH=src python -m zsper brain ingest --profile air ./notes.md
PYTHONPATH=src python -m zsper brain search --profile air notes
```
