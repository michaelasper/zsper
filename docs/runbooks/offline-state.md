# How To Use Offline State

Source references:

- [Ultimate spec](../zsper-local-ai-platform-ultimate-spec.md)
  (`docs/zsper-local-ai-platform-ultimate-spec.md`)
- [Implementation DAG](../superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md)
  (`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`)
- [Profile modes](../architecture/profile-modes.md)
  (`docs/architecture/profile-modes.md`)

Use this guide when a profile needs to keep working without hosted model,
search, extraction, or model-download calls. Offline is a network policy state,
not a profile mode. `work`, `personal`, and `air` profiles can all run in
offline state.

## Install The CLI

Install Zsper first. Installation creates the CLI and home-scoped config; it
does not create a profile or choose a default.

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
```

Create and select a low-compute air profile:

```bash
zsper profile init \
  --mode air \
  --name portable \
  --root "$HOME/.local/share/zsper/profiles/portable"
zsper profile use portable
zsper profile doctor
```

To start that profile in offline state, add `--network-policy offline`:

```bash
zsper profile init \
  --mode air \
  --network-policy offline \
  --name portable \
  --root "$HOME/.local/share/zsper/profiles/portable"
```

The same flag works for `work` and `personal` profiles.

## Prepare From A Source Checkout

From a repository checkout, the setup helper can create the virtual environment,
create or reuse a profile, ingest a readiness note, and verify local search:

```bash
./setup.sh --air --name portable
```

The helper:

- creates `.venv` and a `.venv/bin/zsper` wrapper unless `--no-venv` is used;
- initialises the requested `air` profile in offline state when it is not
  registered;
- reuses the requested profile when it already exists;
- writes `brain/notes/portable-readiness.md` inside the profile root;
- ingests that readiness note through `zsper brain ingest`;
- verifies local search through `zsper brain search`;
- avoids hosted model, search, extraction, and model-download calls.

To run directly from the source checkout without creating `.venv`:

```bash
./setup.sh --air --name portable --no-venv
```

## Choose Explicit Paths

The default registry is `$XDG_CONFIG_HOME/zsper/profiles.json` or
`$HOME/.config/zsper/profiles.json`.

Use explicit paths for laptops, external drives, or disposable profiles:

```bash
./setup.sh --air \
  --name field \
  --root "$HOME/.local/share/zsper/profiles/field" \
  --registry "$HOME/.config/zsper/profiles.json"
```

For automation, the helper honours `ZSPER_AIR_ROOT`, `ZSPER_AIR_NAME`,
`ZSPER_PROFILE_REGISTRY`, and `ZSPER_VENV`.

## Verify Local Use

Inspect the profile:

```bash
zsper profile show --profile portable
```

Run the profile doctor:

```bash
zsper profile doctor --profile portable
```

Ingest a local UTF-8 file:

```bash
zsper brain ingest --profile portable ~/notes/flight.md
```

Search local profile content:

```bash
zsper brain search --profile portable flight
```

URL ingestion is rejected while offline state is active:

```bash
zsper brain ingest --profile portable https://example.com/doc.md
```

## Move To A Laptop

Run the installer after the repository has been copied or cloned onto the
laptop, then create and select the portable profile explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
zsper profile init \
  --mode air \
  --network-policy offline \
  --name portable \
  --root "$HOME/.local/share/zsper/profiles/portable"
zsper profile use portable
```

If you use `./setup.sh --air`, run it on the machine that will use it. The
generated `.venv/bin/zsper` wrapper contains local paths.

To reuse an existing profile, copy the profile root and registry together, then
point the setup helper at those paths:

```bash
./setup.sh --air \
  --name portable \
  --registry "$HOME/.config/zsper/profiles.json" \
  --root "$HOME/.local/share/zsper/profiles/portable"
```

To start clean, copy only the repository and run:

```bash
./setup.sh --air --name portable
```

## Troubleshooting

### Python Version Failure

`setup.sh` requires Python 3.12 or newer.

```bash
PYTHON=python3.12 ./setup.sh --air --name portable
```

### Existing Profile Name Conflict

If a profile name already points to another root, choose a different name and
root:

```bash
./setup.sh --air \
  --name field \
  --root "$HOME/.local/share/zsper/profiles/field"
```

Then use that name in commands:

```bash
zsper brain search --profile field notes
```

### Search Misses A File

Confirm the file is UTF-8 text and was ingested into the same profile:

```bash
zsper profile list
zsper brain ingest --profile portable ./notes.md
zsper brain search --profile portable notes
```
