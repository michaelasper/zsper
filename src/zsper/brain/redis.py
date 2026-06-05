"""Profile-aware Redis runtime configuration for Brain services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


REDIS_RUNTIME_PURPOSES = frozenset({"cache", "job-coordination", "locks"})
CANONICAL_RECORD_TYPES = frozenset(
    {
        "documents",
        "document_chunks",
        "citation_anchors",
        "notes",
        "tasks",
        "memory_events",
        "research_records",
        "chat_sessions",
        "chat_messages",
        "agent_runs",
        "agent_run_events",
        "settings",
        "profile_metadata",
        "ledgers",
    }
)


@dataclass(frozen=True)
class RedisRuntimeConfig:
    profile_id: str
    url: str
    key_prefix: str

    def key(self, *parts: object) -> str:
        suffix = ":".join(str(part).strip(":") for part in parts if str(part))
        return f"{self.key_prefix}{suffix}" if suffix else self.key_prefix.rstrip(":")


def redis_config_from_env(environ: Mapping[str, str]) -> RedisRuntimeConfig:
    profile_id = environ.get("ZSPER_PROFILE_ID") or environ.get("ZSPER_PROFILE_NAME")
    if not profile_id:
        raise ValueError("ZSPER_PROFILE_ID is required for profile-aware Redis config")

    key_prefix = environ.get("REDIS_KEY_PREFIX", f"zsper:{profile_id}:")
    if f":{profile_id}:" not in key_prefix and not key_prefix.endswith(f":{profile_id}"):
        raise ValueError("REDIS_KEY_PREFIX must include the profile id")

    return RedisRuntimeConfig(
        profile_id=profile_id,
        url=environ.get("REDIS_URL", "redis://redis:6379/0"),
        key_prefix=key_prefix,
    )


def redis_is_canonical_storage(record_type: str) -> bool:
    del record_type
    return False
