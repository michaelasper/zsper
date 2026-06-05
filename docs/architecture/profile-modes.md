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
- whether hosted model, search, extraction, or model-download actions are
  blocked;
- which embedding profile is used for local retrieval.

The mode is not the profile name. The profile name is your handle for a concrete
workspace. Examples:

- `work` can be a `work` mode profile named `work`;
- `personal` can be a `personal` mode profile named `personal`;
- `portable`, `field`, or `travel` can be `air-offline` mode profiles.

## Modes

| Mode | Primary use | Storage backend | Network policy | Remote policy |
| --- | --- | --- | --- | --- |
| `work` | Professional projects and private work data | `postgres-pgvector` | `local-first` | `disabled` |
| `personal` | Personal projects and private personal data | `postgres-pgvector` | `local-first` | `tailscale-serve-only` |
| `air-offline` | Portable, disconnected, or lower-compute contexts | `sqlite-local` | `offline` | `disabled` |

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

## Air-Offline Mode

`air-offline` is the portable profile mode. The name describes the policy: the
profile blocks hosted model APIs, hosted search APIs, hosted extraction APIs,
SearXNG queries, URL ingestion, remote access, and model artifact downloads.

This mode is useful beyond flights. Use it for laptops, external-drive
workspaces, disconnected environments, or smaller local runtimes that should not
depend on a higher-compute machine.

The profile name does not need to be `air`.

```bash
zsper profile init \
  --mode air-offline \
  --name portable \
  --root "$HOME/.local/share/zsper/profiles/portable"
zsper profile use portable
```

## Default Values

| Field | `work` | `personal` | `air-offline` |
| --- | --- | --- | --- |
| `model_profile` | `zsper-qwen35-oq6-fp16-mtp-omlx-128k` | `zsper-qwen35-oq6-fp16-mtp-omlx-128k` | `zsper-air-gemma4-12b-it-6bit-128k` |
| `long_context_fallback` | `null` | `zsper-qwen35-oq6-omlx-256k` | `null` |
| `embedding_profile` | `local-bge-small-en-v1.5` | `local-bge-small-en-v1.5` | `local-small-embedding` |
| `storage_backend` | `postgres-pgvector` | `postgres-pgvector` | `sqlite-local` |
| `remote_access_policy` | `disabled` | `tailscale-serve-only` | `disabled` |
| `network_policy` | `local-first` | `local-first` | `offline` |

## Invariants

- Work mode does not use personal remote-access defaults.
- Air-offline mode always uses the offline network policy.
- Tailscale Funnel is forbidden for every mode.
- Hosted model, search, and extraction dependencies are not core flows.
- Profiles with different names or roots must not share Brain records, indexes,
  ledgers, secrets, generated configs, or runtime state.
