from pathlib import Path

import pytest

from zsper.security.hosted_dependencies import (
    HostedDependencyError,
    scan_for_forbidden_hosted_dependencies,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ZSPER = REPO_ROOT / "src" / "zsper"


def test_guard_flags_forbidden_core_runtime_dependency(tmp_path: Path) -> None:
    src = tmp_path / "src" / "zsper"
    src.mkdir(parents=True)
    module = src / "runtime.py"
    module.write_text('HOST = "https://api.openai.com/v1/chat/completions"\n', encoding="utf-8")

    findings = scan_for_forbidden_hosted_dependencies(src)

    assert findings
    assert findings[0].path == module
    assert findings[0].dependency == "api.openai.com"
    with pytest.raises(HostedDependencyError):
        scan_for_forbidden_hosted_dependencies(src, raise_on_findings=True)


def test_guard_ignores_docs_and_future_plugin_metadata(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src" / "zsper" / "plugins").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "src" / "zsper" / "plugins" / "notion.toml").write_text(
        'name = "Notion"\nnetwork = "disabled-by-default"\n',
        encoding="utf-8",
    )
    (root / "docs" / "policy.md").write_text(
        "Future plugin policy may mention Notion or Linear.",
        encoding="utf-8",
    )

    assert scan_for_forbidden_hosted_dependencies(root) == []


def test_current_zsper_source_has_no_forbidden_core_hosted_dependencies() -> None:
    assert scan_for_forbidden_hosted_dependencies(SRC_ZSPER) == []
