"""Detect forbidden hosted dependencies in core Zsper code."""

from __future__ import annotations

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
POLICY_DEFINITION_FILES = frozenset(
    {
        Path("security/hosted_dependencies.py"),
        Path("security/network_policy.py"),
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
    if "plugins" in parts:
        return False
    return True


def _iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return [path for path in root.rglob("*") if path.is_file()]


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
                    findings.append(
                        HostedDependencyFinding(
                            path=path,
                            dependency=dependency,
                            line=line_number,
                            text=line.strip(),
                        )
                    )
    if findings and raise_on_findings:
        first = findings[0]
        raise HostedDependencyError(
            f"forbidden hosted dependency {first.dependency} in "
            f"{first.path}:{first.line}"
        )
    return findings


def find_forbidden_hosted_settings(value: object) -> list[str]:
    rendered = repr(value).lower()
    findings: list[str] = []
    for dependency, needles in FORBIDDEN_DEPENDENCIES.items():
        if any(needle in rendered for needle in needles):
            findings.append(dependency)
    return findings
