"""Profile schema and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILE_MODES = frozenset({"work", "personal", "air-offline"})
STORAGE_BACKENDS = frozenset({"postgres-pgvector", "sqlite-local"})
REMOTE_ACCESS_POLICIES = frozenset({"disabled", "tailscale-serve-only"})
NETWORK_POLICIES = frozenset({"local-first", "offline"})
SCHEMA_VERSION = 1
REQUIRED_PROFILE_FIELDS = (
    "schema_version",
    "name",
    "mode",
    "root",
    "model_profile",
    "long_context_fallback",
    "embedding_profile",
    "storage_backend",
    "remote_access_policy",
    "network_policy",
    "database_name",
    "created_at",
    "updated_at",
)
REQUIRED_STRING_FIELDS = (
    "name",
    "mode",
    "root",
    "model_profile",
    "embedding_profile",
    "storage_backend",
    "remote_access_policy",
    "network_policy",
    "database_name",
    "created_at",
    "updated_at",
)


class ProfileError(ValueError):
    """Raised when a profile is invalid or cannot be resolved."""


@dataclass(frozen=True)
class Profile:
    schema_version: int
    name: str
    mode: str
    root: str
    model_profile: str
    long_context_fallback: str | None
    embedding_profile: str
    storage_backend: str
    remote_access_policy: str
    network_policy: str
    database_name: str
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        if not isinstance(data, dict):
            raise ProfileError("profile JSON must be an object")
        for field in REQUIRED_PROFILE_FIELDS:
            if field not in data:
                raise ProfileError(f"missing required profile field: {field}")

        root = data["root"]
        if not isinstance(root, str) or not root.strip():
            raise ProfileError("profile root must be a non-empty string")

        profile = cls(
            schema_version=data["schema_version"],
            name=data["name"],
            mode=data["mode"],
            root=str(Path(root).expanduser().resolve(strict=False)),
            model_profile=data["model_profile"],
            long_context_fallback=data.get("long_context_fallback"),
            embedding_profile=data["embedding_profile"],
            storage_backend=data["storage_backend"],
            remote_access_policy=data["remote_access_policy"],
            network_policy=data["network_policy"],
            database_name=data["database_name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
        validate_profile(profile)
        return profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "mode": self.mode,
            "root": self.root,
            "model_profile": self.model_profile,
            "long_context_fallback": self.long_context_fallback,
            "embedding_profile": self.embedding_profile,
            "storage_backend": self.storage_backend,
            "remote_access_policy": self.remote_access_policy,
            "network_policy": self.network_policy,
            "database_name": self.database_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def validate_profile(profile: Profile) -> None:
    if not isinstance(profile.schema_version, int) or isinstance(
        profile.schema_version,
        bool,
    ):
        raise ProfileError("profile schema_version must be an integer")
    if profile.schema_version != SCHEMA_VERSION:
        raise ProfileError(f"unsupported profile schema_version: {profile.schema_version}")
    for field in REQUIRED_STRING_FIELDS:
        value = getattr(profile, field)
        if not isinstance(value, str) or not value.strip():
            raise ProfileError(f"profile {field} must be a non-empty string")
    if profile.long_context_fallback is not None and (
        not isinstance(profile.long_context_fallback, str)
        or not profile.long_context_fallback.strip()
    ):
        raise ProfileError("profile long_context_fallback must be a string or null")
    if profile.mode not in PROFILE_MODES:
        raise ProfileError(f"invalid profile mode: {profile.mode}")
    if profile.storage_backend not in STORAGE_BACKENDS:
        raise ProfileError(f"invalid storage_backend: {profile.storage_backend}")
    if profile.remote_access_policy not in REMOTE_ACCESS_POLICIES:
        raise ProfileError(
            f"invalid remote_access_policy: {profile.remote_access_policy}"
        )
    if profile.network_policy not in NETWORK_POLICIES:
        raise ProfileError(f"invalid network_policy: {profile.network_policy}")
    if not Path(profile.root).is_absolute():
        raise ProfileError("profile root must be absolute")
    if profile.mode == "work" and profile.remote_access_policy != "disabled":
        raise ProfileError("work profiles default to disabled remote access")
    if profile.mode == "air-offline" and profile.network_policy != "offline":
        raise ProfileError("air-offline profiles require offline network_policy")
    if profile.mode == "air-offline" and profile.remote_access_policy != "disabled":
        raise ProfileError("air-offline profiles require disabled remote access")
