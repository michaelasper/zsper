"""Resolve profiles by name, root, or profile.json path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from zsper.profiles.registry import registry_entries, registry_path_from_env
from zsper.profiles.schema import Profile, ProfileError


@dataclass(frozen=True)
class ResolvedProfile:
    profile: Profile
    root: Path
    code_dir: Path
    brain_dir: Path
    secrets_dir: Path
    runtime_dir: Path
    agent_runs_dir: Path


def load_profile(root_or_profile_json: Path | str) -> Profile:
    candidate = Path(root_or_profile_json).expanduser().resolve(strict=False)
    profile_path = candidate if candidate.name == "profile.json" else candidate / "profile.json"
    if not profile_path.is_file():
        raise ProfileError(f"profile.json not found at {profile_path}")
    return Profile.from_dict(json.loads(profile_path.read_text(encoding="utf-8")))


def _registry_matches(
    profile: Profile,
    registry_path: Path,
) -> list[dict[str, object]]:
    return [
        entry
        for entry in registry_entries(registry_path)
        if entry.get("name") == profile.name
    ]


def _validate_registry_match(profile: Profile, registry_path: Path) -> None:
    entries = registry_entries(registry_path)
    matches = [entry for entry in entries if entry.get("name") == profile.name]
    if len(matches) > 1:
        raise ProfileError(f"ambiguous profile name: {profile.name}")

    profile_root = Path(profile.root)
    root_matches = [
        entry
        for entry in entries
        if Path(str(entry["root"])).resolve(strict=False) == profile_root
    ]
    if root_matches and root_matches[0].get("name") != profile.name:
        raise ProfileError(
            f"registry entry name mismatch for profile root {profile.root}: "
            f"{root_matches[0].get('name')} != {profile.name}"
        )
    if matches:
        registry_root = Path(str(matches[0]["root"])).resolve(strict=False)
        if registry_root != profile_root:
            raise ProfileError(
                f"registry entry root mismatch for profile {profile.name}: "
                f"{registry_root} != {profile.root}"
            )
    for entry in entries:
        entry_root = Path(str(entry["root"])).resolve(strict=False)
        if entry.get("database_name") == profile.database_name and not (
            entry_root == profile_root and entry.get("name") == profile.name
        ):
            raise ProfileError(
                f"profile database already registered: {profile.database_name}"
            )
        if entry_root != profile_root and profile_root.is_relative_to(entry_root):
            raise ProfileError(
                f"profile root is nested inside registered profile root: {entry_root}"
            )
        if entry_root != profile_root and entry_root.is_relative_to(profile_root):
            raise ProfileError(
                f"registered profile root is nested inside resolved profile root: "
                f"{entry_root}"
            )
    if not matches and not root_matches:
        return
    entry = matches[0] if matches else root_matches[0]
    registry_root = Path(str(entry["root"])).resolve(strict=False)
    if registry_root != profile_root:
        raise ProfileError(
            f"registry entry root mismatch for profile {profile.name}: "
            f"{registry_root} != {profile.root}"
        )


def resolve_profile(
    profile_ref: str | None,
    *,
    registry_path: Path | str | None = None,
) -> Profile:
    if not profile_ref:
        raise ProfileError("profile name or root is required")

    resolved_registry_path = registry_path_from_env(registry_path)
    candidate = Path(profile_ref).expanduser()
    if candidate.name == "profile.json" and candidate.is_file():
        profile = load_profile(candidate)
        _validate_registry_match(profile, resolved_registry_path)
        return profile
    if (candidate / "profile.json").is_file():
        profile = load_profile(candidate)
        _validate_registry_match(profile, resolved_registry_path)
        return profile

    matches = [
        entry
        for entry in registry_entries(resolved_registry_path)
        if entry.get("name") == profile_ref
    ]
    if len(matches) > 1:
        raise ProfileError(f"ambiguous profile name: {profile_ref}")
    if matches:
        profile = load_profile(str(matches[0]["root"]))
        _validate_registry_match(profile, resolved_registry_path)
        return profile

    raise ProfileError(f"profile not found: {profile_ref}")


def resolve_profile_context(
    profile_ref: str | None,
    *,
    registry_path: Path | str | None = None,
) -> ResolvedProfile:
    profile = resolve_profile(profile_ref, registry_path=registry_path)
    root = Path(profile.root)
    return ResolvedProfile(
        profile=profile,
        root=root,
        code_dir=root / "code",
        brain_dir=root / "brain",
        secrets_dir=root / "secrets",
        runtime_dir=root / "runtime",
        agent_runs_dir=root / "agent-runs",
    )
