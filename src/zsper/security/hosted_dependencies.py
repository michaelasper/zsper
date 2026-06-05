"""Detect forbidden hosted dependencies in core Zsper code."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "api.openai.com": ("api.openai.com",),
    "hosted model API": ("hosted-model-api", "hosted model api"),
    "hosted search API": ("hosted-search-api", "hosted search api", "serpapi"),
    "hosted extraction API": (
        "hosted-extraction-api",
        "hosted extraction api",
        "firecrawl",
    ),
    "Notion": ("notion",),
    "Linear": ("linear",),
    "Open WebUI": ("open webui", "open-webui"),
    "Paperclip": ("paperclip",),
    "Ruflo": ("ruflo",),
    "OpenClaw": ("openclaw",),
}
SCANNED_EXTENSIONS = frozenset({".py", ".json", ".toml", ".yaml", ".yml", ".md"})
EXPLICIT_SETTING_KEY_NEEDLES = frozenset(
    {
        "api",
        "apis",
        "base_url",
        "connector",
        "connectors",
        "endpoint",
        "endpoints",
        "host",
        "integration",
        "integrations",
        "plugin",
        "plugins",
        "provider",
        "providers",
        "service",
        "services",
        "uri",
        "url",
    }
)
POLICY_DEFINITION_FILES = frozenset(
    {
        Path("security/hosted_dependencies.py"),
        Path("security/network_policy.py"),
    }
)
PLUGIN_METADATA_FILENAME = "plugin.toml"
PLUGIN_METADATA_REQUIRED_KEYS = frozenset(
    {
        "network_behavior",
        "secret_requirements",
        "profile_scope",
        "disabled_by_default",
    }
)


class HostedDependencyError(RuntimeError):
    """Raised when core code references forbidden hosted dependencies."""


@dataclass(frozen=True)
class HostedDependencyFinding:
    path: Path
    dependency: str
    line: int
    text: str


def _should_scan(path: Path, root: Path) -> bool:
    if path.suffix.lower() not in SCANNED_EXTENSIONS:
        return False
    relative = path.relative_to(root)
    if relative in POLICY_DEFINITION_FILES:
        return False
    parts = set(relative.parts)
    if "docs" in parts:
        return False
    return True


def _iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return [path for path in root.rglob("*") if path.is_file()]


def _is_plugin_path(path: Path, root: Path) -> bool:
    return "plugins" in path.relative_to(root).parts


def _plugin_metadata_candidates(path: Path) -> list[Path]:
    candidates = [path] if path.name == PLUGIN_METADATA_FILENAME else []
    candidates.append(path.parent / PLUGIN_METADATA_FILENAME)
    return candidates


def _plugin_metadata_errors(path: Path) -> list[str]:
    metadata_path = next(
        (candidate for candidate in _plugin_metadata_candidates(path) if candidate.is_file()),
        None,
    )
    if metadata_path is None:
        return [f"missing {PLUGIN_METADATA_FILENAME}"]

    try:
        metadata = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"invalid {PLUGIN_METADATA_FILENAME}: {exc}"]

    missing = sorted(PLUGIN_METADATA_REQUIRED_KEYS - set(metadata))
    errors = [f"missing plugin metadata keys: {', '.join(missing)}"] if missing else []
    if metadata.get("network_behavior") != "disabled-by-default":
        errors.append("plugin metadata network_behavior must be disabled-by-default")
    if metadata.get("profile_scope") != "profile-local":
        errors.append("plugin metadata profile_scope must be profile-local")
    if metadata.get("disabled_by_default") is not True:
        errors.append("plugin metadata disabled_by_default must be true")
    if not metadata.get("secret_requirements"):
        errors.append("plugin metadata secret_requirements must be declared")
    return errors


def scan_for_forbidden_hosted_dependencies(
    root: Path | str,
    *,
    raise_on_findings: bool = False,
) -> list[HostedDependencyFinding]:
    scan_root = Path(root).resolve(strict=False)
    findings: list[HostedDependencyFinding] = []
    for path in _iter_files(scan_root):
        if not _should_scan(path, scan_root):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            for dependency, needles in FORBIDDEN_DEPENDENCIES.items():
                if any(needle in lowered for needle in needles):
                    if _is_plugin_path(path, scan_root):
                        errors = _plugin_metadata_errors(path)
                        if not errors:
                            continue
                        finding_text = (
                            f"{line.strip()} "
                            f"(plugin metadata invalid: {'; '.join(errors)})"
                        )
                    else:
                        finding_text = line.strip()
                    findings.append(
                        HostedDependencyFinding(
                            path=path,
                            dependency=dependency,
                            line=line_number,
                            text=finding_text,
                        )
                    )
    if findings and raise_on_findings:
        first = findings[0]
        raise HostedDependencyError(
            f"forbidden hosted dependency {first.dependency} in "
            f"{first.path}:{first.line}"
        )
    return findings


def _looks_like_url(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(("http://", "https://"))


def _is_explicit_settings_key(key: str) -> bool:
    lowered = key.lower()
    if any(needle in lowered for needle in EXPLICIT_SETTING_KEY_NEEDLES):
        return True
    return any(
        needle in lowered
        for needles in FORBIDDEN_DEPENDENCIES.values()
        for needle in needles
    )


def _iter_hosted_setting_text(value: object, *, explicit: bool = False) -> list[str]:
    if isinstance(value, dict):
        texts: list[str] = []
        for key, child in value.items():
            key_text = str(key)
            child_explicit = explicit or _is_explicit_settings_key(key_text)
            if child_explicit:
                texts.append(key_text.lower())
            texts.extend(
                _iter_hosted_setting_text(child, explicit=child_explicit)
            )
        return texts

    if isinstance(value, (list, tuple, set)):
        texts = []
        for item in value:
            texts.extend(_iter_hosted_setting_text(item, explicit=explicit))
        return texts

    if isinstance(value, str):
        if explicit or _looks_like_url(value):
            return [value.lower()]
        return []

    if explicit and value is not None:
        return [repr(value).lower()]
    return []


def find_forbidden_hosted_settings(value: object) -> list[str]:
    rendered_settings = _iter_hosted_setting_text(value)
    findings: list[str] = []
    for dependency, needles in FORBIDDEN_DEPENDENCIES.items():
        if any(
            needle in rendered
            for rendered in rendered_settings
            for needle in needles
        ):
            findings.append(dependency)
    return findings
