"""Mode defaults for Zsper profiles."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from zsper.profiles.schema import Profile, ProfileError, SCHEMA_VERSION


MODE_DEFAULTS: dict[str, dict[str, str | None]] = {
    "work": {
        "name": "work",
        "model_profile": "zsper-qwen35-oq6-fp16-mtp-omlx-128k",
        "long_context_fallback": None,
        "embedding_profile": "local-bge-small-en-v1.5",
        "storage_backend": "postgres-pgvector",
        "remote_access_policy": "disabled",
        "network_policy": "local-first",
        "database_name": "zsper_work",
    },
    "personal": {
        "name": "personal",
        "model_profile": "zsper-qwen35-oq6-fp16-mtp-omlx-128k",
        "long_context_fallback": "zsper-qwen35-oq6-omlx-256k",
        "embedding_profile": "local-bge-small-en-v1.5",
        "storage_backend": "postgres-pgvector",
        "remote_access_policy": "tailscale-serve-only",
        "network_policy": "local-first",
        "database_name": "zsper_personal",
    },
    "air-offline": {
        "name": "air",
        "model_profile": "zsper-air-gemma4-12b-it-6bit-128k",
        "long_context_fallback": None,
        "embedding_profile": "local-small-embedding",
        "storage_backend": "sqlite-local",
        "remote_access_policy": "disabled",
        "network_policy": "offline",
        "database_name": "zsper_air_offline",
    },
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _database_name_for_profile(
    default_database_name: str,
    default_profile_name: str,
    profile_name: str,
) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", profile_name.lower()).strip("_")
    if not slug:
        raise ProfileError("profile name must contain at least one alphanumeric character")
    if profile_name == default_profile_name:
        return default_database_name
    return f"zsper_{slug}"


def default_profile(
    *,
    mode: str,
    root: Path | str,
    name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> Profile:
    if mode not in MODE_DEFAULTS:
        raise ProfileError(f"invalid profile mode: {mode}")

    overrides = overrides or {}
    defaults = {**MODE_DEFAULTS[mode], **overrides}
    profile_name = name or str(defaults["name"])
    database_name = (
        str(defaults["database_name"])
        if "database_name" in overrides
        else _database_name_for_profile(
            str(defaults["database_name"]),
            str(defaults["name"]),
            profile_name,
        )
    )
    now = utc_now()
    return Profile.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "name": profile_name,
            "mode": mode,
            "root": str(Path(root).expanduser().resolve(strict=False)),
            "model_profile": defaults["model_profile"],
            "long_context_fallback": defaults["long_context_fallback"],
            "embedding_profile": defaults["embedding_profile"],
            "storage_backend": defaults["storage_backend"],
            "remote_access_policy": defaults["remote_access_policy"],
            "network_policy": defaults["network_policy"],
            "database_name": database_name,
            "created_at": now,
            "updated_at": now,
        }
    )
