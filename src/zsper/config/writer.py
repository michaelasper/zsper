"""Safe profile-local config writing."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zsper.profiles import Profile
from zsper.security.redaction import redact_secrets


LOCAL_SENTINEL_API_KEY = "zsper-local-only"


class ConfigWriteError(RuntimeError):
    """Raised when config writing would leave the allowed profile scope."""


@dataclass(frozen=True)
class GlobalPatchResult:
    target_path: Path
    backup_path: Path | None
    redacted_diff: str


class ProfileConfigWriter:
    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self.code_root = Path(profile.root).resolve(strict=False) / "code"

    def _target_path(self, relative_path: str | Path) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ConfigWriteError("config writes must stay under profile-local code directory")
        target = (self.code_root / candidate).resolve(strict=False)
        if target != self.code_root and not target.is_relative_to(self.code_root):
            raise ConfigWriteError("config writes must stay under profile-local code directory")
        return target

    def write_json(self, relative_path: str | Path, payload: dict[str, Any]) -> Path:
        target = self._target_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target

    def write_yaml(self, relative_path: str | Path, payload: dict[str, Any]) -> Path:
        target = self._target_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render_yaml(payload), encoding="utf-8")
        return target

    def write_text(self, relative_path: str | Path, content: str) -> Path:
        target = self._target_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target


def _render_yaml(value: Any, *, indent: int = 0) -> str:
    lines: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            nested = value[key]
            prefix = " " * indent
            if isinstance(nested, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(_render_yaml(nested, indent=indent + 2).rstrip("\n"))
            elif isinstance(nested, list):
                lines.append(f"{prefix}{key}:")
                for item in nested:
                    lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{key}: {nested}")
    else:
        lines.append(f"{' ' * indent}{value}")
    return "\n".join(lines) + "\n"


def _redact_text(content: str) -> str:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return _redact_secret_lines(content)
    return json.dumps(redact_secrets(parsed), sort_keys=True)


def _redact_secret_lines(content: str) -> str:
    secret_pattern = re.compile(
        r"(?i)^(\s*[\"']?(?:apiKey|api_key|token|authorization|password|secret)[\"']?\s*[:=]\s*)(.*)$"
    )
    redacted_lines: list[str] = []
    for line in content.splitlines():
        match = secret_pattern.match(line)
        if match:
            redacted_lines.append(f"{match.group(1)}[REDACTED]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)


def patch_global_config(target: Path | str, new_content: str) -> GlobalPatchResult:
    target_path = Path(target).expanduser().resolve(strict=False)
    old_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    backup_path: Path | None = None
    if target_path.exists():
        backup_path = target_path.with_suffix(target_path.suffix + ".bak")
        backup_path.write_text(old_content, encoding="utf-8")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(new_content, encoding="utf-8")
    redacted_old = _redact_text(old_content)
    redacted_new = _redact_text(new_content)
    redacted_diff = "\n".join(
        difflib.unified_diff(
            redacted_old.splitlines(),
            redacted_new.splitlines(),
            fromfile=str(backup_path or target_path),
            tofile=str(target_path),
            lineterm="",
        )
    )
    return GlobalPatchResult(
        target_path=target_path,
        backup_path=backup_path,
        redacted_diff=redacted_diff,
    )
