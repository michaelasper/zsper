import json
from pathlib import Path

import pytest

from zsper.profiles import (
    PROFILE_LAYOUT_DIRS,
    ProfileError,
    default_profile,
    initialize_profile,
    load_profile,
    profile_doctor,
    resolve_profile,
)


def test_air_profile_defaults_match_spec(tmp_path: Path) -> None:
    profile = default_profile(mode="air", root=tmp_path / "air")

    assert profile.schema_version == 1
    assert profile.name == "air"
    assert profile.mode == "air"
    assert profile.root == str((tmp_path / "air").resolve())
    assert profile.remote_access_policy == "disabled"
    assert profile.network_policy == "local-first"
    assert profile.model_profile == "zsper-air-gemma4-12b-it-6bit-128k"
    assert profile.long_context_fallback is None
    assert profile.storage_backend == "sqlite-local"
    assert profile.embedding_profile == "local-small-embedding"
    assert profile.database_name == "zsper_air"


def test_initialize_air_profile_writes_profile_layout_and_registry(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    root = tmp_path / "profiles" / "air"

    profile = initialize_profile(
        mode="air",
        root=root,
        registry_path=isolated_registry_path,
    )

    assert profile.name == "air"
    assert (root / "profile.json").is_file()
    for relative_dir in PROFILE_LAYOUT_DIRS:
        assert (root / relative_dir).is_dir(), relative_dir
    assert (root / "agent-runs" / "runs.jsonl").read_text(encoding="utf-8") == ""

    profile_json = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    assert profile_json["mode"] == "air"
    assert profile_json["network_policy"] == "local-first"

    registry_json = json.loads(isolated_registry_path.read_text(encoding="utf-8"))
    assert registry_json["profiles"][0]["name"] == "air"
    assert registry_json["profiles"][0]["root"] == str(root.resolve())


def test_initialize_profile_refuses_existing_profile_root(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    root = tmp_path / "profiles" / "air"
    initialize_profile(
        mode="air",
        root=root,
        registry_path=isolated_registry_path,
    )

    with pytest.raises(ProfileError, match="already contains profile.json"):
        initialize_profile(
            mode="air",
            root=root,
            registry_path=isolated_registry_path,
        )


def test_initialize_profile_registry_conflict_does_not_dirty_new_root(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    first_root = tmp_path / "profiles" / "air-one"
    second_root = tmp_path / "profiles" / "air-two"
    initialize_profile(
        mode="air",
        root=first_root,
        registry_path=isolated_registry_path,
    )

    with pytest.raises(ProfileError, match="profile name already registered: air"):
        initialize_profile(
            mode="air",
            root=second_root,
            registry_path=isolated_registry_path,
        )

    assert not (second_root / "profile.json").exists()


def test_resolve_and_doctor_air_profile(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    root = tmp_path / "profiles" / "air"
    initialize_profile(
        mode="air",
        root=root,
        registry_path=isolated_registry_path,
    )

    resolved = resolve_profile("air", registry_path=isolated_registry_path)
    loaded = load_profile(root)
    report = profile_doctor("air", registry_path=isolated_registry_path)

    assert resolved.root == str(root.resolve())
    assert loaded.mode == "air"
    assert report.ok is True
    assert report.profile.name == "air"
    assert report.errors == []


def test_air_profile_can_start_in_offline_degraded_state(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    root = tmp_path / "profiles" / "air"

    profile = initialize_profile(
        mode="air",
        root=root,
        registry_path=isolated_registry_path,
        network_policy="offline",
    )

    assert profile.mode == "air"
    assert profile.network_policy == "offline"
    assert json.loads((root / "profile.json").read_text(encoding="utf-8"))[
        "network_policy"
    ] == "offline"
