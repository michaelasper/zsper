from pathlib import Path

import pytest

from zsper.profiles.schema import Profile, ProfileError, validate_profile


def profile_payload(root: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "name": "work",
        "mode": "work",
        "root": str(root),
        "model_profile": "zsper-qwen35-oq6-fp16-mtp-omlx-128k",
        "long_context_fallback": None,
        "embedding_profile": "local-bge-small-en-v1.5",
        "storage_backend": "postgres-pgvector",
        "remote_access_policy": "disabled",
        "network_policy": "local-first",
        "database_name": "zsper_work",
        "created_at": "2026-06-04T00:00:00+00:00",
        "updated_at": "2026-06-04T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def test_profile_json_round_trips_and_normalizes_root(tmp_path: Path) -> None:
    relative_root = tmp_path / ".." / tmp_path.name / "work"

    profile = Profile.from_dict(profile_payload(relative_root))

    assert profile.root == str((tmp_path / "work").resolve(strict=False))
    assert Profile.from_dict(profile.to_dict()) == profile


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mode", "team", "invalid profile mode"),
        ("storage_backend", "s3", "invalid storage_backend"),
        ("remote_access_policy", "tailscale-funnel", "invalid remote_access_policy"),
        ("network_policy", "hosted-first", "invalid network_policy"),
    ],
)
def test_invalid_enum_values_fail_validation(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    with pytest.raises(ProfileError, match=message):
        Profile.from_dict(profile_payload(tmp_path / "profile", **{field: value}))


def test_validate_profile_rejects_relative_root() -> None:
    profile = Profile(
        schema_version=1,
        name="work",
        mode="work",
        root="relative/root",
        model_profile="zsper-qwen35-oq6-fp16-mtp-omlx-128k",
        long_context_fallback=None,
        embedding_profile="local-bge-small-en-v1.5",
        storage_backend="postgres-pgvector",
        remote_access_policy="disabled",
        network_policy="local-first",
        database_name="zsper_work",
        created_at="2026-06-04T00:00:00+00:00",
        updated_at="2026-06-04T00:00:00+00:00",
    )

    with pytest.raises(ProfileError, match="profile root must be absolute"):
        validate_profile(profile)
