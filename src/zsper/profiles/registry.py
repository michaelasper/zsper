"""Profile registry helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from zsper.profiles.schema import Profile, ProfileError, SCHEMA_VERSION


def registry_path_from_env(registry_path: Path | str | None = None) -> Path:
    if registry_path is not None:
        return Path(registry_path).expanduser().resolve(strict=False)

    env_path = os.environ.get("ZSPER_PROFILE_REGISTRY")
    if env_path:
        return Path(env_path).expanduser().resolve(strict=False)

    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (config_home / "zsper" / "profiles.json").resolve(strict=False)


def read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def registry_entries(registry_path: Path | str | None = None) -> list[dict[str, Any]]:
    registry = read_registry(registry_path_from_env(registry_path))
    return list(registry.get("profiles", []))


def validated_registry_with_entries(
    profile: Profile,
    registry_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    registry = read_registry(registry_path)
    entries = registry.setdefault("profiles", [])
    profile_root = Path(profile.root).resolve(strict=False)
    for entry in entries:
        if entry["name"] == profile.name:
            raise ProfileError(f"profile name already registered: {profile.name}")
        if entry.get("database_name") == profile.database_name:
            raise ProfileError(
                f"profile database already registered: {profile.database_name}"
            )
        entry_root = Path(entry["root"]).resolve(strict=False)
        if entry_root == profile_root:
            raise ProfileError(f"profile root already registered: {profile.root}")
        if profile_root.is_relative_to(entry_root):
            raise ProfileError(
                f"profile root is nested inside registered profile root: {entry_root}"
            )
        if entry_root.is_relative_to(profile_root):
            raise ProfileError(
                f"registered profile root is nested inside new profile root: {entry_root}"
            )

    return registry, entries


def register_profile(profile: Profile, registry_path: Path) -> None:
    registry, entries = validated_registry_with_entries(profile, registry_path)
    entries.append(
        {
            "name": profile.name,
            "mode": profile.mode,
            "root": profile.root,
            "database_name": profile.database_name,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
    )
    write_registry(registry_path, registry)


def list_profiles(registry_path: Path | str | None = None) -> list[Profile]:
    from zsper.profiles.resolver import load_profile

    profiles: list[Profile] = []
    for entry in registry_entries(registry_path):
        profiles.append(load_profile(entry["root"]))
    return profiles
