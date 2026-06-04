"""Profile schema, defaults, registry, and initialization helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROFILE_LAYOUT_DIRS: tuple[Path, ...] = (
    Path("secrets"),
    Path("runtime/code"),
    Path("runtime/brain"),
    Path("runtime/agents"),
    Path("models/huggingface"),
    Path("models/embeddings"),
    Path("code/zed"),
    Path("code/opencode"),
    Path("code/pi"),
    Path("code/hermes"),
    Path("brain/assets"),
    Path("brain/parsed"),
    Path("brain/ledgers"),
    Path("brain/notes"),
    Path("brain/tasks"),
    Path("brain/memory"),
    Path("brain/documents"),
    Path("brain/citations"),
    Path("agent-runs/events"),
    Path("agent-runs/artifacts"),
    Path("agent-runs/summaries"),
    Path("logs"),
)
PROFILE_MODES = frozenset({"work", "personal", "air-offline"})
STORAGE_BACKENDS = frozenset({"postgres-pgvector", "sqlite-local"})
REMOTE_ACCESS_POLICIES = frozenset({"disabled", "tailscale-serve-only"})
NETWORK_POLICIES = frozenset({"local-first", "offline"})
SCHEMA_VERSION = 1

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
        profile = cls(
            schema_version=data["schema_version"],
            name=data["name"],
            mode=data["mode"],
            root=str(Path(data["root"]).expanduser().resolve(strict=False)),
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


@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    profile: Profile
    errors: list[str]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def validate_profile(profile: Profile) -> None:
    if profile.schema_version != SCHEMA_VERSION:
        raise ProfileError(f"unsupported profile schema_version: {profile.schema_version}")
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


def default_profile(
    *,
    mode: str,
    root: Path | str,
    name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> Profile:
    if mode not in MODE_DEFAULTS:
        raise ProfileError(f"invalid profile mode: {mode}")

    defaults = {**MODE_DEFAULTS[mode], **(overrides or {})}
    now = _utc_now()
    profile = Profile.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "name": name or defaults["name"],
            "mode": mode,
            "root": str(Path(root).expanduser().resolve(strict=False)),
            "model_profile": defaults["model_profile"],
            "long_context_fallback": defaults["long_context_fallback"],
            "embedding_profile": defaults["embedding_profile"],
            "storage_backend": defaults["storage_backend"],
            "remote_access_policy": defaults["remote_access_policy"],
            "network_policy": defaults["network_policy"],
            "database_name": defaults["database_name"],
            "created_at": now,
            "updated_at": now,
        }
    )
    return profile


def registry_path_from_env(registry_path: Path | str | None = None) -> Path:
    if registry_path is not None:
        return Path(registry_path).expanduser().resolve(strict=False)

    env_path = os.environ.get("ZSPER_PROFILE_REGISTRY")
    if env_path:
        return Path(env_path).expanduser().resolve(strict=False)

    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (config_home / "zsper" / "profiles.json").resolve(strict=False)


def load_profile(root: Path | str) -> Profile:
    root_path = Path(root).expanduser().resolve(strict=False)
    profile_path = root_path / "profile.json"
    if not profile_path.is_file():
        raise ProfileError(f"profile.json not found at {profile_path}")
    return Profile.from_dict(json.loads(profile_path.read_text(encoding="utf-8")))


def _write_profile(profile: Profile) -> None:
    profile_path = Path(profile.root) / "profile.json"
    profile_path.write_text(
        json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _register_profile(profile: Profile, registry_path: Path) -> None:
    registry, entries = _validated_registry_with_entries(profile, registry_path)
    entries.append(
        {
            "name": profile.name,
            "mode": profile.mode,
            "root": profile.root,
            "created_at": profile.created_at,
        }
    )
    _write_registry(registry_path, registry)


def _validated_registry_with_entries(
    profile: Profile,
    registry_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    registry = _read_registry(registry_path)
    entries = registry.setdefault("profiles", [])
    for entry in entries:
        if entry["name"] == profile.name:
            raise ProfileError(f"profile name already registered: {profile.name}")
        if Path(entry["root"]).resolve(strict=False) == Path(profile.root):
            raise ProfileError(f"profile root already registered: {profile.root}")

    return registry, entries


def initialize_profile(
    *,
    mode: str,
    root: Path | str,
    registry_path: Path | str | None = None,
    name: str | None = None,
) -> Profile:
    profile = default_profile(mode=mode, root=root, name=name)
    root_path = Path(profile.root)
    if (root_path / "profile.json").exists():
        raise ProfileError(f"{root_path} already contains profile.json")

    resolved_registry_path = registry_path_from_env(registry_path)
    _validated_registry_with_entries(profile, resolved_registry_path)

    root_path.mkdir(parents=True, exist_ok=True)
    for relative_dir in PROFILE_LAYOUT_DIRS:
        (root_path / relative_dir).mkdir(parents=True, exist_ok=True)
    (root_path / "agent-runs" / "runs.jsonl").touch()
    _write_profile(profile)
    _register_profile(profile, resolved_registry_path)
    return profile


def list_profiles(registry_path: Path | str | None = None) -> list[Profile]:
    registry = _read_registry(registry_path_from_env(registry_path))
    profiles: list[Profile] = []
    for entry in registry.get("profiles", []):
        profiles.append(load_profile(entry["root"]))
    return profiles


def resolve_profile(
    profile_ref: str | None,
    *,
    registry_path: Path | str | None = None,
) -> Profile:
    if not profile_ref:
        raise ProfileError("profile name or root is required")

    candidate = Path(profile_ref).expanduser()
    if (candidate / "profile.json").is_file():
        return load_profile(candidate)

    registry = _read_registry(registry_path_from_env(registry_path))
    for entry in registry.get("profiles", []):
        if entry["name"] == profile_ref:
            return load_profile(entry["root"])

    raise ProfileError(f"profile not found: {profile_ref}")


def profile_doctor(
    profile_ref: str,
    *,
    registry_path: Path | str | None = None,
) -> DoctorReport:
    profile = resolve_profile(profile_ref, registry_path=registry_path)
    root = Path(profile.root)
    errors: list[str] = []

    try:
        validate_profile(profile)
    except ProfileError as exc:
        errors.append(str(exc))

    if not (root / "profile.json").is_file():
        errors.append("missing profile.json")
    for relative_dir in PROFILE_LAYOUT_DIRS:
        if not (root / relative_dir).is_dir():
            errors.append(f"missing directory: {relative_dir}")
    if not (root / "agent-runs" / "runs.jsonl").is_file():
        errors.append("missing agent-runs/runs.jsonl")

    return DoctorReport(ok=not errors, profile=profile, errors=errors)
