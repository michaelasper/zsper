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


def test_guard_allows_declared_disabled_by_default_plugin_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    plugin = root / "src" / "zsper" / "plugins" / "notion"
    plugin.mkdir(parents=True)
    (root / "docs").mkdir()
    (plugin / "plugin.toml").write_text(
        "\n".join(
            [
                'name = "Notion"',
                'network_behavior = "disabled-by-default"',
                'secret_requirements = "declared"',
                'profile_scope = "profile-local"',
                "disabled_by_default = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plugin / "adapter.py").write_text(
        'SERVICE = "Notion"\n',
        encoding="utf-8",
    )
    (root / "docs" / "policy.md").write_text(
        "Future plugin policy may mention Notion or Linear.",
        encoding="utf-8",
    )

    assert scan_for_forbidden_hosted_dependencies(root) == []


def test_guard_flags_plugin_references_without_required_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    plugin = root / "src" / "zsper" / "plugins" / "notion"
    plugin.mkdir(parents=True)
    adapter = plugin / "adapter.py"
    adapter.write_text('SERVICE = "Notion"\n', encoding="utf-8")

    findings = scan_for_forbidden_hosted_dependencies(root)

    assert findings
    assert findings[0].path == adapter
    assert findings[0].dependency == "Notion"
    assert "plugin metadata" in findings[0].text


def test_current_zsper_source_has_no_forbidden_core_hosted_dependencies() -> None:
    assert scan_for_forbidden_hosted_dependencies(SRC_ZSPER) == []
