from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from zsper.brain.compose import brain_ports_for_profile
from zsper.brain.rag_commands import components_for_profile
from zsper.cli import app
from zsper.profiles import initialize_profile
from zsper.rag import ProfileRagStore
from zsper.rag.indexes import ProfileVectorIndex


@pytest.fixture(autouse=True)
def fake_embedding_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from zsper.profiles import Profile
    from zsper.rag.embeddings import DeterministicFakeEmbeddingProvider

    def provider_for_profile(profile: Profile) -> DeterministicFakeEmbeddingProvider:
        return DeterministicFakeEmbeddingProvider(model=profile.embedding_profile)

    monkeypatch.setattr(
        "zsper.brain.rag_commands.provider_for_profile",
        provider_for_profile,
    )


def _init_profile(
    monkeypatch: pytest.MonkeyPatch,
    isolated_registry_path: Path,
    tmp_path: Path,
    *,
    mode: str = "work",
    sqlite_overrides: bool = True,
    network_policy: str | None = None,
) -> Path:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("ZSPER_RAG_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_BM25_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_VECTOR_SQLITE_PATH", raising=False)
    if sqlite_overrides:
        monkeypatch.setenv("ZSPER_RAG_SQLITE_PATH", str(tmp_path / mode / "rag.sqlite"))
        monkeypatch.setenv(
            "ZSPER_VECTOR_SQLITE_PATH",
            str(tmp_path / mode / "vectors.sqlite"),
        )
    profile = initialize_profile(
        mode=mode,
        root=tmp_path / mode,
        registry_path=isolated_registry_path,
        network_policy=network_policy,
    )
    return Path(profile.root)


def _markdown_fixture(tmp_path: Path) -> Path:
    source = tmp_path / "fixture.md"
    source.write_text(
        "# Operations\n\n"
        "Restart the profile worker from the runtime directory before checking "
        "status. The recovery note belongs in the local brain index.\n",
        encoding="utf-8",
    )
    return source


def _repo_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "fixture-repo"
    docs = repo / "docs"
    ignored = repo / ".git"
    docs.mkdir(parents=True)
    ignored.mkdir()
    (repo / "README.md").write_text(
        "# Fixture Repo\n\nRepo ingestion keeps air profile sources local.\n",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text(
        "# Air Guide\n\nThe portable cabin checklist confirms repo docs ingestion.\n",
        encoding="utf-8",
    )
    (ignored / "config").write_text("do not index git internals\n", encoding="utf-8")
    return repo


def test_markdown_fixture_ingests_and_searches_through_cli(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile_root = _init_profile(
        monkeypatch,
        isolated_registry_path,
        tmp_path,
    )
    source = _markdown_fixture(tmp_path)

    assert app(["brain", "ingest", str(source), "--profile", str(profile_root)]) == 0
    ingest = capsys.readouterr()
    assert ingest.err == ""
    assert "ingested document" in ingest.out
    assert "\t1 chunks" in ingest.out

    assert app(["brain", "search", "profile", "worker", "--profile", "work"]) == 0
    search = capsys.readouterr()
    assert search.err == ""
    assert "Restart the profile worker" in search.out
    assert str(source) in search.out
    assert "\tchunk-" in search.out
    assert "\tanchor-" in search.out


def test_repo_directory_ingests_and_searches_through_cli(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _init_profile(
        monkeypatch,
        isolated_registry_path,
        tmp_path,
    )
    repo = _repo_fixture(tmp_path)

    assert app(["brain", "ingest", str(repo), "--profile", "work"]) == 0
    ingest = capsys.readouterr()
    assert ingest.err == ""
    assert "ingested document" in ingest.out
    assert str(repo.resolve()) in ingest.out

    assert app(["brain", "search", "portable", "cabin", "--profile", "work"]) == 0
    search = capsys.readouterr()
    assert search.err == ""
    assert "portable cabin checklist" in search.out
    assert str(repo.resolve()) in search.out


def test_answer_cli_returns_citation_objects_from_ingested_markdown(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _init_profile(monkeypatch, isolated_registry_path, tmp_path)
    source = _markdown_fixture(tmp_path)

    assert app(["brain", "ingest", str(source), "--profile", "work"]) == 0
    capsys.readouterr()

    def fake_create_chat_completion(
        self: object,
        *,
        url: str,
        payload: Mapping[str, object],
        timeout: float,
    ) -> Mapping[str, object]:
        del self, url, timeout
        messages = payload["messages"]
        assert isinstance(messages, list)
        user_message = messages[1]
        assert isinstance(user_message, dict)
        prompt = json.loads(str(user_message["content"]))
        citation_anchor_id = prompt["context"][0]["citation_anchor_id"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "Restart the profile worker first.",
                                "answer_confidence": 0.82,
                                "citation_anchor_ids": [citation_anchor_id],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "zsper.rag.answer.OpenAICompatibleAnswerModelClient.create_chat_completion",
        fake_create_chat_completion,
    )

    assert app(["brain", "answer", "profile", "worker", "--profile", "work"]) == 0
    captured = capsys.readouterr()

    assert captured.err == ""
    body = json.loads(captured.out)
    assert body["text"] == "Restart the profile worker first."
    assert body["answer_confidence"] == 0.82
    assert body["citations"][0]["source_path_or_url"] == str(source)
    assert body["citations"][0]["citation_anchor_id"].startswith("anchor-")
    assert body["citations"][0]["chunk_id"].startswith("chunk-")
    assert body["citations"][0]["display_range"].startswith("bytes ")


def test_offline_ingest_rejects_urls_before_web_capture(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _init_profile(
        monkeypatch,
        isolated_registry_path,
        tmp_path,
        mode="air",
        network_policy="offline",
    )

    assert (
        app(["brain", "ingest", "https://example.com/research", "--profile", "air"])
        == 1
    )
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "offline policy blocks url-ingest" in captured.err


def test_rag_cli_rejects_hosted_postgres_dsn_before_connecting(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _init_profile(monkeypatch, isolated_registry_path, tmp_path)
    monkeypatch.setenv(
        "POSTGRES_DSN",
        "postgresql://zsper:secret@db.example.com:5432/zsper_work",
    )

    assert app(["brain", "search", "profile", "worker", "--profile", "work"]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "Postgres DSN must point at a local service" in captured.err


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql:///zsper_work?host=db.example.com",
        "postgresql://127.0.0.1/zsper_work?hostaddr=203.0.113.10",
    ],
)
def test_rag_cli_rejects_hosted_libpq_dsn_query_params_before_connecting(
    dsn: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _init_profile(monkeypatch, isolated_registry_path, tmp_path)
    monkeypatch.setenv("POSTGRES_DSN", dsn)

    assert app(["brain", "search", "profile", "worker", "--profile", "work"]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "Postgres DSN must point at a local service" in captured.err


def test_rag_cli_uses_profile_postgres_backend_without_exported_dsn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("ZSPER_RAG_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_BM25_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_VECTOR_SQLITE_PATH", raising=False)
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store_dsns: list[str] = []
    vector_dsns: list[str] = []

    def fake_store_postgres_dsn(dsn: str) -> ProfileRagStore:
        store_dsns.append(dsn)
        return ProfileRagStore(
            database_path=None,
            backend="postgres",
            connection_factory=lambda: None,
        )

    def fake_vector_postgres_dsn(dsn: str) -> ProfileVectorIndex:
        vector_dsns.append(dsn)
        return ProfileVectorIndex(
            database_path=None,
            backend="postgres",
            connection_factory=lambda: None,
        )

    monkeypatch.setattr(
        "zsper.brain.rag_commands.ProfileRagStore.postgres_dsn",
        fake_store_postgres_dsn,
    )
    monkeypatch.setattr(
        "zsper.brain.rag_commands.ProfileVectorIndex.postgres_dsn",
        fake_vector_postgres_dsn,
    )

    components = components_for_profile(profile)

    ports = brain_ports_for_profile(profile)
    expected_dsn = (
        "postgresql://zsper:zsper-local-only@"
        f"127.0.0.1:{ports.postgres}/{profile.database_name}"
    )
    assert store_dsns == [expected_dsn]
    assert vector_dsns == [expected_dsn]
    assert components.store.backend == "postgres"
    assert components.vector_index.backend == "postgres"


def test_brain_rag_help_describes_implemented_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert app(["brain", "ingest", "--help"]) == 0
    captured = capsys.readouterr()

    assert "Ingest a source into the profile RAG index." in captured.out
    assert "reserved for a later implementation task" not in captured.out
    assert "when this command is implemented" not in captured.out
