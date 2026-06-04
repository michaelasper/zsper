from pathlib import Path

import pytest

from zsper.profiles.defaults import default_profile
from zsper.profiles.schema import ProfileError


def test_work_personal_and_air_defaults_match_spec(tmp_path: Path) -> None:
    work = default_profile(mode="work", root=tmp_path / "work")
    personal = default_profile(mode="personal", root=tmp_path / "personal")
    air = default_profile(mode="air-offline", root=tmp_path / "air")

    assert work.remote_access_policy == "disabled"
    assert work.network_policy == "local-first"
    assert work.model_profile == "zsper-qwen35-oq6-fp16-mtp-omlx-128k"
    assert work.long_context_fallback is None
    assert work.storage_backend == "postgres-pgvector"
    assert work.embedding_profile == "local-bge-small-en-v1.5"

    assert personal.remote_access_policy == "tailscale-serve-only"
    assert personal.network_policy == "local-first"
    assert personal.model_profile == "zsper-qwen35-oq6-fp16-mtp-omlx-128k"
    assert personal.long_context_fallback == "zsper-qwen35-oq6-omlx-256k"
    assert personal.storage_backend == "postgres-pgvector"
    assert personal.embedding_profile == "local-bge-small-en-v1.5"

    assert air.remote_access_policy == "disabled"
    assert air.network_policy == "offline"
    assert air.model_profile == "zsper-air-gemma4-12b-it-6bit-128k"
    assert air.long_context_fallback is None
    assert air.storage_backend == "sqlite-local"
    assert air.embedding_profile == "local-small-embedding"


def test_invalid_mode_policy_combinations_fail_before_filesystem_use(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="work profiles default to disabled"):
        default_profile(
            mode="work",
            root=tmp_path / "work",
            overrides={"remote_access_policy": "tailscale-serve-only"},
        )

    with pytest.raises(ProfileError, match="air-offline profiles require offline"):
        default_profile(
            mode="air-offline",
            root=tmp_path / "air",
            overrides={"network_policy": "local-first"},
        )


def test_custom_profile_names_get_distinct_database_names(tmp_path: Path) -> None:
    first = default_profile(mode="work", root=tmp_path / "one", name="work-one")
    second = default_profile(mode="work", root=tmp_path / "two", name="work-two")

    assert first.database_name == "zsper_work_one"
    assert second.database_name == "zsper_work_two"
