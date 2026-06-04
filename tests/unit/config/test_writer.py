import json
from pathlib import Path

import pytest

from zsper.config.writer import (
    LOCAL_SENTINEL_API_KEY,
    ConfigWriteError,
    ProfileConfigWriter,
    patch_global_config,
)
from zsper.profiles import default_profile


def test_profile_writer_writes_deterministic_json_yaml_and_text(tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    writer = ProfileConfigWriter(profile)

    json_path = writer.write_json("zed/settings.json", {"b": 2, "a": 1})
    yaml_path = writer.write_yaml(
        "pi/provider.yml",
        {"provider": {"model": profile.model_profile, "api_key": LOCAL_SENTINEL_API_KEY}},
    )
    text_path = writer.write_text("pi/AGENTS.md", "local model\n")

    assert json_path == Path(profile.root) / "code" / "zed" / "settings.json"
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert json_path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'
    assert yaml_path.read_text(encoding="utf-8") == (
        "provider:\n"
        f"  api_key: {LOCAL_SENTINEL_API_KEY}\n"
        f"  model: {profile.model_profile}\n"
    )
    assert text_path.read_text(encoding="utf-8") == "local model\n"


@pytest.mark.parametrize(
    "relative_path",
    [
        "../secrets/model.env",
        "zed/../../secrets/model.env",
        "/tmp/global-settings.json",
    ],
)
def test_profile_writer_refuses_paths_outside_profile_code_root(
    tmp_path: Path,
    relative_path: str,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    writer = ProfileConfigWriter(profile)

    with pytest.raises(ConfigWriteError, match="profile-local code directory"):
        writer.write_text(relative_path, "nope\n")


def test_global_patch_api_writes_backup_and_returns_redacted_diff(tmp_path: Path) -> None:
    target = tmp_path / "global" / "opencode.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps({"apiKey": "sk-old-secret", "model": "old"}, sort_keys=True),
        encoding="utf-8",
    )

    result = patch_global_config(
        target,
        json.dumps({"apiKey": "sk-new-secret", "model": "new"}, sort_keys=True),
    )

    assert target.read_text(encoding="utf-8") == '{"apiKey": "sk-new-secret", "model": "new"}'
    assert result.backup_path is not None
    assert result.backup_path.read_text(encoding="utf-8") == (
        '{"apiKey": "sk-old-secret", "model": "old"}'
    )
    assert "sk-old-secret" not in result.redacted_diff
    assert "sk-new-secret" not in result.redacted_diff
    assert '"apiKey": "[REDACTED]"' in result.redacted_diff
    assert "model" in result.redacted_diff


def test_global_patch_api_redacts_non_json_secret_values(tmp_path: Path) -> None:
    target = tmp_path / "global" / "provider.yml"
    target.parent.mkdir(parents=True)
    target.write_text("api_key: old-secret\nmodel: old\n", encoding="utf-8")

    result = patch_global_config(target, "api_key: new-secret\nmodel: new\n")

    assert "old-secret" not in result.redacted_diff
    assert "new-secret" not in result.redacted_diff
    assert "api_key: [REDACTED]" in result.redacted_diff
    assert "model: new" in result.redacted_diff


def test_global_patch_api_redacts_quoted_non_json_secret_keys(tmp_path: Path) -> None:
    target = tmp_path / "global" / "provider.toml"
    target.parent.mkdir(parents=True)
    target.write_text('"apiKey" = "old-secret"\nmodel = "old"\n', encoding="utf-8")

    result = patch_global_config(target, '"apiKey" = "new-secret"\nmodel = "new"\n')

    assert "old-secret" not in result.redacted_diff
    assert "new-secret" not in result.redacted_diff
    assert '"apiKey" = [REDACTED]' in result.redacted_diff
