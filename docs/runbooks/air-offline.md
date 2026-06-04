# How To Prepare An Air/Offline Profile

Source references:

- [Ultimate spec](../zsper-local-ai-platform-ultimate-spec.md)
  (`docs/zsper-local-ai-platform-ultimate-spec.md`)
- [Implementation DAG](../superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md)
  (`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`)

Use this guide when you need the `air` profile ready for local work before the
full Brain/RAG/orchestrator milestones are complete. The current path prepares
profile-local storage, verifies local file ingest, and checks exact offline
search. Model downloads and model serving stay outside this repository.

## Prepare The Profile

Run the setup script from the repository root:

```bash
./setup.sh --air
```

The script:

- creates `.venv` and a `.venv/bin/zsper` wrapper unless `--no-venv` is used;
- initialises the `air` profile when it is not already registered;
- reuses an existing registered `air` profile when it exists;
- writes `brain/notes/air-readiness.md` inside the profile root;
- ingests that readiness note through `zsper brain ingest --profile air`;
- verifies local search through `zsper brain search --profile air offline`;
- avoids model downloads and hosted API calls.

If you want to run directly from the source checkout without creating `.venv`,
use:

```bash
./setup.sh --air --no-venv
```

## Choose Explicit Paths

The default registry is `$XDG_CONFIG_HOME/zsper/profiles.json` or
`$HOME/.config/zsper/profiles.json`. The default profile root is
`$XDG_DATA_HOME/zsper/profiles/air` or
`$HOME/.local/share/zsper/profiles/air`.

Use explicit paths when preparing a laptop, an external drive, or a disposable
test profile:

```bash
./setup.sh --air \
  --registry "$HOME/.config/zsper/profiles.json" \
  --root "$HOME/.local/share/zsper/profiles/air"
```

The same values can be supplied with environment variables:

```bash
export ZSPER_PROFILE_REGISTRY="$HOME/.config/zsper/profiles.json"
export ZSPER_AIR_ROOT="$HOME/.local/share/zsper/profiles/air"
export ZSPER_VENV="$PWD/.venv"
./setup.sh --air
```

## Verify Local Use

Inspect the profile:

```bash
PYTHONPATH=src python -m zsper profile show --profile air
```

Run the profile doctor:

```bash
PYTHONPATH=src python -m zsper profile doctor --profile air
```

Ingest a local UTF-8 file:

```bash
PYTHONPATH=src python -m zsper brain ingest --profile air ~/notes/flight.md
```

Search local profile content:

```bash
PYTHONPATH=src python -m zsper brain search --profile air flight
```

URLs are rejected for air/offline ingest:

```bash
PYTHONPATH=src python -m zsper brain ingest --profile air https://example.com/doc.md
```

## Move To A Laptop

Run `./setup.sh --air` after the repository has been copied or cloned onto the
laptop. The generated `.venv/bin/zsper` wrapper contains local paths, so it
should be created on the machine that will use it.

If the laptop should reuse an existing air profile, copy the profile root and
registry together, then point the setup script at those paths:

```bash
./setup.sh --air \
  --registry "$HOME/.config/zsper/profiles.json" \
  --root "$HOME/.local/share/zsper/profiles/air"
```

If the laptop should start clean, copy only the repository and run:

```bash
./setup.sh --air
```

## Troubleshooting

### Python Version Failure

`setup.sh` requires Python 3.12 or newer because the package metadata requires
it.

```bash
PYTHON=python3.12 ./setup.sh --air
```

### Existing Profile Name Conflict

If `air` already points to another root, the script uses the registered profile.
Create a second profile with an explicit name:

```bash
./setup.sh --air --name air-laptop --root "$HOME/.local/share/zsper/profiles/air-laptop"
```

Then use that name in commands:

```bash
PYTHONPATH=src python -m zsper brain search --profile air-laptop offline
```

### Search Misses A File

Confirm the file is UTF-8 text and was ingested into the same registry:

```bash
PYTHONPATH=src python -m zsper profile list
PYTHONPATH=src python -m zsper brain ingest --profile air ./notes.md
PYTHONPATH=src python -m zsper brain search --profile air notes
```

The current MVP search is exact token search. Punctuation is treated as a
delimiter, so `notes.`, `charger-ready`, and `offline/search` can be found with
`notes`, `charger`, and `search`.
