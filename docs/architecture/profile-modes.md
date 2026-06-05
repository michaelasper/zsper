# Profile Modes

Source references:

- [Ultimate spec](../zsper-local-ai-platform-ultimate-spec.md)
  (`docs/zsper-local-ai-platform-ultimate-spec.md`)
- [Implementation DAG](../superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md)
  (`docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`)

This is an explanation and reference for Zsper profile modes. Use it to decide
which mode to create and to understand the defaults each mode applies.

## What A Mode Controls

A profile is the isolation boundary. Its mode chooses the default policies and
runtime shape for that boundary:

- where Brain records and RAG indexes are stored;
- which model endpoint identity the profile expects;
- whether remote access is allowed;
- which embedding profile is used for local retrieval.

Network policy is separate from mode.

Offline is a network-policy state, not a mode. `local-first` is the normal
state; `offline` is a degraded state that any mode can use when hosted calls,
URL ingestion, SearXNG queries, and model artifact downloads must be blocked.

The mode is not the profile name. The profile name is your handle for a concrete
workspace. Examples:

- `work` can be a `work` mode profile named `work`;
- `personal` can be a `personal` mode profile named `personal`;
- `portable`, `field`, or `travel` can be `air` mode profiles.

## Modes

| Mode | Primary use | Storage backend | Network policy | Remote policy |
| --- | --- | --- | --- | --- |
| `work` | Professional projects and private work data | `postgres-pgvector` | `local-first` | `disabled` |
| `personal` | Personal projects and private personal data | `postgres-pgvector` | `local-first` | `tailscale-serve-only` |
| `air` | Portable or lower-compute contexts | `sqlite-local` | `local-first` | `disabled` |

## Work Mode

Work mode is the conservative local profile for professional data. It uses local
Postgres + pgvector for Brain and RAG storage, blocks remote exposure by
default, and expects local model serving through the `zsper-code` endpoint
contract.

Create a work profile when the data should stay on the workstation and should
not inherit personal remote-access defaults.

```bash
zsper profile init --mode work --root "$HOME/.local/share/zsper/profiles/work"
zsper profile use work
```

## Personal Mode

Personal mode keeps the same local-first storage model as work mode, but its
default remote-access policy permits Tailscale Serve. Tailscale Funnel remains
forbidden.

Create a personal profile when private personal data should be isolated from
work data and may need private tailnet access.

```bash
zsper profile init \
  --mode personal \
  --root "$HOME/.local/share/zsper/profiles/personal"
zsper profile use personal
```

## Air Mode

Air mode is the low-compute profile mode. Use it for laptops, external-drive
workspaces, or smaller local runtimes that should not depend on a higher-compute
machine.

The profile name does not need to be `air`.

```bash
zsper profile init \
  --mode air \
  --name portable \
  --root "$HOME/.local/share/zsper/profiles/portable"
zsper profile use portable
```

## Offline State

Offline state is selected with `network_policy=offline`. It blocks hosted model
APIs, hosted search APIs, hosted extraction APIs, SearXNG queries, URL
ingestion, plugin network access, and model artifact downloads. Local files and
localhost services remain allowed.

Any mode can start offline:

```bash
zsper profile init \
  --mode work \
  --network-policy offline \
  --root "$HOME/.local/share/zsper/profiles/work"
```

## Default Values

| Field | `work` | `personal` | `air` |
| --- | --- | --- | --- |
| `model_profile` | `zsper-qwen35-oq6-fp16-mtp-omlx-128k` | `zsper-qwen35-oq6-fp16-mtp-omlx-128k` | `zsper-air-gemma4-12b-it-6bit-128k` |
| `long_context_fallback` | `null` | `zsper-qwen35-oq6-omlx-256k` | `null` |
| `embedding_profile` | `local-bge-small-en-v1.5` | `local-bge-small-en-v1.5` | `local-small-embedding` |
| `storage_backend` | `postgres-pgvector` | `postgres-pgvector` | `sqlite-local` |
| `remote_access_policy` | `disabled` | `tailscale-serve-only` | `disabled` |
| `network_policy` | `local-first` | `local-first` | `local-first` |

## Invariants

- Work mode does not use personal remote-access defaults.
- Air mode always uses disabled remote access.
- Offline state can be used by work, personal, and air profiles.
- Tailscale Funnel is forbidden for every mode.
- Hosted model, search, and extraction dependencies are not core flows.
- Profiles with different names or roots must not share Brain records, indexes,
  ledgers, secrets, generated configs, or runtime state.
