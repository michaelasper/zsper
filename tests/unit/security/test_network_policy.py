from pathlib import Path

import pytest

from zsper.security.network_policy import NetworkPolicyError, check_network_policy


def test_offline_policy_allows_local_files_and_localhost_services(tmp_path: Path) -> None:
    local_file = tmp_path / "notes.md"
    local_file.write_text("offline notes", encoding="utf-8")

    file_decision = check_network_policy(
        "offline",
        str(local_file),
        action="local-file-read",
    )
    localhost_decision = check_network_policy(
        "offline",
        "http://127.0.0.1:9127/v1/models",
        action="localhost-service",
    )

    assert file_decision.allowed is True
    assert localhost_decision.allowed is True


@pytest.mark.parametrize(
    ("target", "action"),
    [
        ("https://example.com/doc.md", "url-ingest"),
        ("http://localhost:8080/search?q=flight", "searxng-query"),
        ("https://api.openai.com/v1/chat/completions", "hosted-model-api"),
        ("https://serpapi.com/search", "hosted-search-api"),
        ("https://api.firecrawl.dev/v1/scrape", "hosted-extraction-api"),
        ("https://huggingface.co/google/gemma", "model-artifact-download"),
        ("https://notion.so/workspace", "plugin-network"),
    ],
)
def test_offline_policy_blocks_networked_and_hosted_actions(
    target: str,
    action: str,
) -> None:
    decision = check_network_policy("offline", target, action=action)

    assert decision.allowed is False
    with pytest.raises(NetworkPolicyError):
        decision.raise_for_status()


def test_local_first_still_blocks_hosted_integrations_without_plugin_policy() -> None:
    hosted_model = check_network_policy(
        "local-first",
        "https://api.openai.com/v1/chat/completions",
        action="hosted-model-api",
    )
    plugin_network = check_network_policy(
        "local-first",
        "https://notion.so/workspace",
        action="plugin-network",
    )

    assert hosted_model.allowed is False
    assert plugin_network.allowed is False


def test_local_first_allows_explicit_user_web_capture_and_local_searxng() -> None:
    web_capture = check_network_policy(
        "local-first",
        "https://example.com/doc.md",
        action="url-ingest",
        user_triggered=True,
    )
    searxng = check_network_policy(
        "local-first",
        "http://127.0.0.1:8080/search?q=local",
        action="searxng-query",
        local_searxng=True,
    )

    assert web_capture.allowed is True
    assert searxng.allowed is True
