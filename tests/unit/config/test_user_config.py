from pathlib import Path

import pytest

from zsper.config.user import (
    UserConfigError,
    config_path_from_env,
    default_profile_name,
    profile_ref_or_default,
    set_default_profile,
)


def test_user_config_defaults_to_xdg_home(monkeypatch, tmp_path: Path) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("ZSPER_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ZSPER_CONFIG_FILE", raising=False)

    assert config_path_from_env() == config_home / "zsper" / "config.toml"
    assert default_profile_name() is None


def test_set_default_profile_writes_home_config(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "config" / "zsper" / "config.toml"
    monkeypatch.setenv("ZSPER_CONFIG_FILE", str(config_file))

    written_path = set_default_profile("work")

    assert written_path == config_file
    assert default_profile_name() == "work"
    assert 'default_profile = "work"' in config_file.read_text(encoding="utf-8")


def test_profile_ref_or_default_requires_explicit_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_CONFIG_FILE", str(tmp_path / "config.toml"))

    assert profile_ref_or_default("personal") == "personal"
    with pytest.raises(UserConfigError) as exc_info:
        profile_ref_or_default(None)

    assert str(exc_info.value) == (
        "no default profile configured; run zsper profile use NAME or pass --profile NAME"
    )
