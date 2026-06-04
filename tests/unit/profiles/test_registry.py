import json
from pathlib import Path

import pytest

from zsper.profiles.init import initialize_profile
from zsper.profiles.registry import list_profiles, registry_path_from_env
from zsper.profiles.schema import ProfileError


def test_registry_path_comes_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "config" / "profiles.json"
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(registry))

    assert registry_path_from_env() == registry.resolve(strict=False)


def test_registry_entries_include_profile_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )

    registry = json.loads(isolated_registry_path.read_text(encoding="utf-8"))
    entry = registry["profiles"][0]

    assert entry["name"] == "work"
    assert entry["mode"] == "work"
    assert entry["root"] == profile.root
    assert entry["database_name"] == "zsper_work"
    assert entry["created_at"] == profile.created_at
    assert entry["updated_at"] == profile.updated_at
    assert "secret" not in json.dumps(entry).lower()


def test_registry_duplicate_name_fails_before_mutation(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    initialize_profile(
        mode="work",
        root=tmp_path / "work-one",
        registry_path=isolated_registry_path,
    )
    before = isolated_registry_path.read_text(encoding="utf-8")

    with pytest.raises(ProfileError, match="profile name already registered: work"):
        initialize_profile(
            mode="work",
            root=tmp_path / "work-two",
            registry_path=isolated_registry_path,
        )

    assert isolated_registry_path.read_text(encoding="utf-8") == before


def test_registry_rejects_duplicate_database_names_after_slugging(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    initialize_profile(
        mode="work",
        name="work-one",
        root=tmp_path / "work-one",
        registry_path=isolated_registry_path,
    )

    with pytest.raises(ProfileError, match="profile database already registered"):
        initialize_profile(
            mode="work",
            name="work_one",
            root=tmp_path / "work-two",
            registry_path=isolated_registry_path,
        )


def test_registry_rejects_nested_profile_roots(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    first = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )

    with pytest.raises(ProfileError, match="nested inside registered profile root"):
        initialize_profile(
            mode="work",
            name="work-nested",
            root=Path(first.root) / "nested-work",
            registry_path=isolated_registry_path,
        )


def test_list_profiles_reads_initialized_profiles(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )

    assert [profile.name for profile in list_profiles(isolated_registry_path)] == [
        "work",
        "personal",
    ]
