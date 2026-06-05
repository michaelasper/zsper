"""Profile root initialization."""

from __future__ import annotations

import json
from pathlib import Path

from zsper.profiles.defaults import default_profile
from zsper.profiles.registry import (
    register_profile,
    registry_path_from_env,
    validated_registry_with_entries,
)
from zsper.profiles.schema import Profile, ProfileError


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


def write_profile(profile: Profile) -> None:
    profile_path = Path(profile.root) / "profile.json"
    profile_path.write_text(
        json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def initialize_profile(
    *,
    mode: str,
    root: Path | str,
    registry_path: Path | str | None = None,
    name: str | None = None,
    network_policy: str | None = None,
) -> Profile:
    overrides = {"network_policy": network_policy} if network_policy is not None else None
    profile = default_profile(mode=mode, root=root, name=name, overrides=overrides)
    root_path = Path(profile.root)
    if (root_path / "profile.json").exists():
        raise ProfileError(f"{root_path} already contains profile.json")

    resolved_registry_path = registry_path_from_env(registry_path)
    validated_registry_with_entries(profile, resolved_registry_path)

    root_path.mkdir(parents=True, exist_ok=True)
    for relative_dir in PROFILE_LAYOUT_DIRS:
        (root_path / relative_dir).mkdir(parents=True, exist_ok=True)
    (root_path / "agent-runs" / "runs.jsonl").touch()
    write_profile(profile)
    register_profile(profile, resolved_registry_path)
    return profile
