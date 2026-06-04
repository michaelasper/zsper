import json
from pathlib import Path

import pytest

from zsper.profiles.defaults import default_profile
from zsper.profiles.init import initialize_profile, write_profile
from zsper.profiles.resolver import resolve_profile, resolve_profile_context
from zsper.profiles.schema import ProfileError


def test_resolver_accepts_name_root_and_profile_json_path(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    created = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    root = Path(created.root)

    assert resolve_profile("work", registry_path=isolated_registry_path).root == created.root
    assert resolve_profile(str(root), registry_path=isolated_registry_path).root == created.root
    assert (
        resolve_profile(str(root / "profile.json"), registry_path=isolated_registry_path).root
        == created.root
    )


def test_resolver_returns_profile_local_paths(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    created = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )

    resolved = resolve_profile_context("personal", registry_path=isolated_registry_path)

    assert resolved.profile.root == created.root
    assert resolved.root == Path(created.root)
    assert resolved.code_dir == Path(created.root) / "code"
    assert resolved.brain_dir == Path(created.root) / "brain"
    assert resolved.secrets_dir == Path(created.root) / "secrets"


def test_resolver_refuses_registry_metadata_mismatch(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    created = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    registry = json.loads(isolated_registry_path.read_text(encoding="utf-8"))
    registry["profiles"][0]["root"] = str(tmp_path / "other-root")
    isolated_registry_path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(ProfileError, match="registry entry root mismatch"):
        resolve_profile(created.root, registry_path=isolated_registry_path)


def test_resolver_refuses_registered_root_with_mutated_profile_name(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    created = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    profile_path = Path(created.root) / "profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["name"] = "personal"
    profile_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProfileError, match="registry entry name mismatch"):
        resolve_profile(created.root, registry_path=isolated_registry_path)


def test_resolver_refuses_unregistered_nested_profile_root(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    created = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    nested = default_profile(
        mode="work",
        name="work-nested",
        root=Path(created.root) / "nested-work",
    )
    Path(nested.root).mkdir(parents=True)
    write_profile(nested)

    with pytest.raises(ProfileError, match="nested inside registered profile root"):
        resolve_profile(nested.root, registry_path=isolated_registry_path)


def test_resolver_refuses_unregistered_profile_database_reuse(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    unregistered = default_profile(
        mode="work",
        name="work-alias",
        root=tmp_path / "work-alias",
        overrides={"database_name": "zsper_work"},
    )
    Path(unregistered.root).mkdir(parents=True)
    write_profile(unregistered)

    with pytest.raises(ProfileError, match="profile database already registered"):
        resolve_profile(unregistered.root, registry_path=isolated_registry_path)


def test_resolver_requires_profile_reference() -> None:
    with pytest.raises(ProfileError, match="profile name or root is required"):
        resolve_profile(None)
