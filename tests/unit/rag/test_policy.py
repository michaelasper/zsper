from pathlib import Path
from typing import Any

import pytest

from zsper.profiles import default_profile
from zsper.rag import RagPolicyError as ExportedRagPolicyError
from zsper.rag import RagPolicyGate as ExportedRagPolicyGate
from zsper.rag.policy import RagPolicyError, RagPolicyGate


def _profile(mode: str, tmp_path: Path):
    return default_profile(mode=mode, root=tmp_path / mode)


def test_air_offline_url_ingest_fails_before_http_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[Any, ...]] = []

    def forbidden_urlopen(*args: Any, **kwargs: Any) -> None:
        calls.append(args)
        raise AssertionError("policy test must not make HTTP calls")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_urlopen)
    gate = RagPolicyGate(_profile("air-offline", tmp_path))

    with pytest.raises(RagPolicyError, match="offline policy blocks url-ingest"):
        gate.require_ingest(
            "https://example.com/research.md",
            user_triggered=True,
        )

    assert calls == []


def test_rag_policy_gate_is_exported_from_rag_package() -> None:
    assert ExportedRagPolicyGate is RagPolicyGate
    assert ExportedRagPolicyError is RagPolicyError


def test_air_offline_rejects_searxng_before_search_http_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[Any, ...]] = []

    def forbidden_urlopen(*args: Any, **kwargs: Any) -> None:
        calls.append(args)
        raise AssertionError("policy test must not make HTTP calls")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_urlopen)
    gate = RagPolicyGate(_profile("air-offline", tmp_path))

    with pytest.raises(RagPolicyError, match="offline policy blocks searxng-query"):
        gate.require_search(
            searxng_url="http://127.0.0.1:8080/search?q=local-first",
        )

    assert calls == []


@pytest.mark.parametrize(
    ("action", "target"),
    [
        ("hosted-extraction-api", "https://api.firecrawl.dev/v1/scrape"),
        ("hosted-model-api", "https://api.openai.com/v1/chat/completions"),
        ("hosted-search-api", "https://serpapi.com/search?q=rag"),
        ("model-artifact-download", "https://huggingface.co/google/gemma"),
    ],
)
def test_air_offline_rejects_hosted_rag_dependencies(
    tmp_path: Path,
    action: str,
    target: str,
) -> None:
    gate = RagPolicyGate(_profile("air-offline", tmp_path))

    with pytest.raises(RagPolicyError, match=f"offline policy blocks {action}"):
        gate.require_hosted_dependency(target, action=action)


def test_rag_policy_rejects_forbidden_hosted_settings(tmp_path: Path) -> None:
    gate = RagPolicyGate(_profile("work", tmp_path))

    with pytest.raises(RagPolicyError) as exc_info:
        gate.require_no_hosted_settings(
            {
                "model": {"base_url": "https://api.openai.com/v1"},
                "search": {"provider": "serpapi"},
                "extraction": {"provider": "firecrawl"},
            }
        )

    message = str(exc_info.value)
    assert "forbidden hosted RAG settings" in message
    assert "api.openai.com" in message
    assert "hosted search API" in message
    assert "hosted extraction API" in message


def test_local_first_permits_explicit_web_capture_and_local_searxng(
    tmp_path: Path,
) -> None:
    gate = RagPolicyGate(_profile("work", tmp_path))

    gate.require_ingest("https://example.com/research.md", user_triggered=True)
    gate.require_search(searxng_url="http://127.0.0.1:8080/search?q=rag")


def test_local_first_rejects_implicit_url_ingest(tmp_path: Path) -> None:
    gate = RagPolicyGate(_profile("work", tmp_path))

    with pytest.raises(RagPolicyError, match="local-first policy blocks url-ingest"):
        gate.require_ingest("https://example.com/research.md")
