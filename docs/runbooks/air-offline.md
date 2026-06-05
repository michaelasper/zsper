# How To Prepare A Portable/Air Profile

Source references:

- [Ultimate spec](../zsper-local-ai-platform-ultimate-spec.md)
  (`docs/zsper-local-ai-platform-ultimate-spec.md`)
- [Implementation DAG](../superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md)
  (`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`)

Use this guide when you need an `air` profile ready for portable or lower-compute
local work before the full Brain/RAG/orchestrator milestones are complete. Air
does not mean it must be the install default. In the current MVP, the
`air-offline` mode blocks hosted model, search, and extraction calls until a
local laptop runtime is configured.

## Install The CLI

Install Zsper first. Installation is profile-neutral: it creates the CLI and
home-scoped config, but it does not create a profile and does not choose a
default profile.

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
```

Create and select the air profile explicitly:

```bash
zsper profile init --mode air-offline --root "$HOME/.local/share/zsper/profiles/air" --name air
zsper profile use air
zsper profile doctor
```

## Prepare From A Source Checkout

If you are already working from the repository, the setup helper can prepare the
current air MVP:

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
zsper profile init \
  --mode air-offline \
  --name air-laptop \
  --root "$HOME/.local/share/zsper/profiles/air-laptop"
zsper profile use air-laptop
```

For automation, the source setup helper also honors `ZSPER_AIR_ROOT`,
`ZSPER_AIR_NAME`, `ZSPER_PROFILE_REGISTRY`, and `ZSPER_VENV`.

## Verify Local Use

Inspect the profile:

```bash
zsper profile show --profile air
```

Run the profile doctor:

```bash
zsper profile doctor --profile air
```

Ingest a local UTF-8 file:

```bash
zsper brain ingest --profile air ~/notes/flight.md
```

Search local profile content:

```bash
zsper brain search --profile air flight
```

URLs are rejected while the current `air-offline` mode is active:

```bash
zsper brain ingest --profile air https://example.com/doc.md
```

## Move To A Laptop

Run the installer after the repository has been copied or cloned onto the laptop,
then create/select the air profile explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/michaelasper/zsper/main/install.sh | bash
zsper profile init --mode air-offline --root "$HOME/.local/share/zsper/profiles/air" --name air
zsper profile use air
```

If you use `./setup.sh --air`, run it on the machine that will use it. The
generated `.venv/bin/zsper` wrapper contains local paths.

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
zsper brain search --profile air-laptop offline
```

### Search Misses A File

Confirm the file is UTF-8 text and was ingested into the same registry:

```bash
zsper profile list
zsper brain ingest --profile air ./notes.md
zsper brain search --profile air notes
```

The current MVP search is exact token search. Punctuation is treated as a
delimiter, so `notes.`, `charger-ready`, and `offline/search` can be found with
`notes`, `charger`, and `search`.
