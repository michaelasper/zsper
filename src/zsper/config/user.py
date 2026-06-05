"""Home-scoped user config for Zsper CLI defaults."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_MISSING_MESSAGE = (
    "no default profile configured; run zsper profile use NAME or pass --profile NAME"
)


class UserConfigError(RuntimeError):
    """Raised when the home-scoped user config cannot provide a value."""


def config_path_from_env(config_path: Path | str | None = None) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser().resolve(strict=False)

    env_config_file = os.environ.get("ZSPER_CONFIG_FILE")
    if env_config_file:
        return Path(env_config_file).expanduser().resolve(strict=False)

    env_config_dir = os.environ.get("ZSPER_CONFIG_DIR")
    if env_config_dir:
        return (
            Path(env_config_dir).expanduser().resolve(strict=False) / "config.toml"
        )

    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (config_home / "zsper" / "config.toml").resolve(strict=False)


def load_user_config(config_path: Path | str | None = None) -> dict[str, Any]:
    path = config_path_from_env(config_path)
    if not path.exists():
        return {}
    try:
        return dict(tomllib.loads(path.read_text(encoding="utf-8")))
    except tomllib.TOMLDecodeError as exc:
        raise UserConfigError(f"invalid Zsper config at {path}: {exc}") from exc


def default_profile_name(config_path: Path | str | None = None) -> str | None:
    value = load_user_config(config_path).get("default_profile")
    return value if isinstance(value, str) and value else None


def profile_ref_or_default(
    explicit_profile_ref: str | None,
    *,
    config_path: Path | str | None = None,
) -> str:
    if explicit_profile_ref:
        return explicit_profile_ref

    configured_default = default_profile_name(config_path)
    if configured_default:
        return configured_default

    raise UserConfigError(DEFAULT_PROFILE_MISSING_MESSAGE)


def set_default_profile(
    profile_name: str,
    *,
    config_path: Path | str | None = None,
) -> Path:
    path = config_path_from_env(config_path)
    config = load_user_config(path)
    config["default_profile"] = profile_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_toml(config), encoding="utf-8")
    return path


def _render_toml(config: dict[str, Any]) -> str:
    lines = [
        "# Zsper user config",
        "# Set with: zsper profile use NAME",
        "",
    ]
    for key in sorted(config):
        value = config[key]
        if isinstance(value, bool):
            rendered_value = "true" if value else "false"
        elif isinstance(value, int):
            rendered_value = str(value)
        elif isinstance(value, str):
            rendered_value = json.dumps(value)
        else:
            continue
        lines.append(f"{key} = {rendered_value}")
    return "\n".join(lines) + "\n"
