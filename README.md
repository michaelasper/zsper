# Zsper

<p align="center">
  <b>Local-first AI workflows that keep profile data isolated and usable offline.</b>
</p>

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"
zsper profile use work
```

## TL;DR

**Problem:** local AI work often mixes personal, work, travel, model-serving,
and agent state until it is hard to trust what data moved where.

**Solution:** Zsper gives each workflow a profile boundary, a CLI surface, and
profile-local Brain storage. The current MVP keeps install profile-neutral:
create work, personal, or portable/air profiles after the CLI is installed.

| Feature | Benefit |
| --- | --- |
| Profile-neutral install | Install the CLI without silently choosing a profile. |
| Portable/air setup | Prepare an isolated lower-compute travel profile explicitly. |
| Profile-local Brain files | Ingest and search UTF-8 local files without hosted calls. |
| Explicit boundaries | Keep product code in `zsper` and model serving in `llm-server`. |
| Append-only ledgers | Record Brain file mutations in profile-local JSONL. |

## Quick Start

```bash
# 1. Install the CLI into your home directory.
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash

# 2. Create a profile. Installation does not create one for you.
zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"

# 3. Choose the default profile for commands that omit --profile.
zsper profile use work

# 4. Ingest a local UTF-8 file.
zsper brain ingest ~/notes/flight.md

# 5. Search local profile content.
zsper brain search offline

# 6. Verify the profile layout.
zsper profile doctor
```

For the portable/air workflow, use
[docs/runbooks/air-offline.md](docs/runbooks/air-offline.md).

## What Works Now

| Workflow | Example |
| --- | --- |
| Install CLI | `curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh \| bash` |
| Initialise profiles | `zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"` |
| Choose default profile | `zsper profile use work` |
| List profiles | `zsper profile list` |
| Inspect a profile | `zsper profile show` |
| Doctor a profile | `zsper profile doctor` |
| Ingest local text | `zsper brain ingest ./notes.md` |
| Search local text | `zsper brain search notes` |

`./setup.sh --air` creates a project virtual environment by default, writes a
small `zsper` wrapper into `.venv/bin/`, initialises or reuses the air profile,
ingests a readiness note, and verifies offline search. It does not download
models or call hosted APIs. It is a repository-local helper; the polished
installer is `install.sh`.

## Installation And Setup

### Polished install

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
```

The installer clones or updates Zsper under `~/.local/share/zsper/app`, creates
a managed virtual environment under `~/.local/share/zsper/venv`, writes
`~/.local/bin/zsper`, and creates home-scoped config files under
`~/.config/zsper`. It does not create a profile or set a default.

After installing, create the profile you want:

```bash
zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"
zsper profile use work
```

For a portable/air profile on a laptop or lower-compute machine:

```bash
zsper profile init --mode air-offline --root "$HOME/.local/share/zsper/profiles/air" --name air
zsper profile use air
```

The current MVP mode name is `air-offline` because hosted model, search, and
extraction calls are blocked until a local laptop runtime is configured. The
profile itself is not the install default.

### Source checkout for development

```bash
git clone https://github.com/michaelasper/zsper.git
cd zsper
python -m pip install -e .
zsper --help
```

### Editable package install

```bash
python -m pip install -e .
zsper --help
```

Use the editable install when network and Python packaging dependencies are
available. The air setup script keeps the current MVP usable from source on a
travel machine:

```bash
./setup.sh --air
```

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
| Portable/air setup | [docs/runbooks/air-offline.md](docs/runbooks/air-offline.md) |
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

### `install.sh` or `./setup.sh --air` says Python is too old

Install Python 3.12 or newer, then rerun:

```bash
PYTHON=python3.12 ./setup.sh --air
```

For the installer, make sure `python3.12` is on `PATH`.

### The `air` profile already exists

The setup script reuses an existing registered `air` profile. To create a
separate air profile root, choose a different name and root:

```bash
./setup.sh --air --name air-laptop --root "$HOME/.local/share/zsper/profiles/air-laptop"
```

### Search returns no results

Confirm the file was ingested into the same profile registry:

```bash
zsper profile list
zsper brain ingest --profile air ./notes.md
zsper brain search --profile air notes
```
