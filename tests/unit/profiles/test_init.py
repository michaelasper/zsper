from pathlib import Path

import pytest

from zsper.profiles.init import PROFILE_LAYOUT_DIRS, initialize_profile
from zsper.profiles.schema import ProfileError


def test_work_and_personal_roots_have_identical_directory_shape(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    personal = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )

    for profile in (work, personal):
        root = Path(profile.root)
        assert (root / "profile.json").is_file()
        assert (root / "agent-runs" / "runs.jsonl").is_file()
        for relative_dir in PROFILE_LAYOUT_DIRS:
            assert (root / relative_dir).is_dir(), relative_dir


def test_runtime_deletion_does_not_remove_canonical_profile_data(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    root = Path(profile.root)

    for canonical_path in (
        root / "profile.json",
        root / "secrets",
        root / "brain",
        root / "agent-runs",
    ):
        assert canonical_path.exists()


def test_duplicate_root_initialization_fails_clearly(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    root = tmp_path / "work"
    initialize_profile(mode="work", root=root, registry_path=isolated_registry_path)

    with pytest.raises(ProfileError, match="already contains profile.json"):
        initialize_profile(mode="work", root=root, registry_path=isolated_registry_path)
