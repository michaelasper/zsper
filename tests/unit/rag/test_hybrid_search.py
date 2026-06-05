from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag import HybridSearchError
from zsper.rag.indexes import ProfileBm25Index, ProfileVectorIndex
from zsper.rag.indexes import VectorIndexError
from zsper.rag.models import CitationAnchor, Document, DocumentChunk
from zsper.rag.store import ProfileRagStore


@pytest.fixture(autouse=True)
def fake_cli_embedding_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeQueryEmbeddingProvider:
        def __init__(self, model: str) -> None:
            self.model = model

        def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
            return tuple((1.0,) + ((0.0,) * 383) for _ in texts)

    def provider_for_profile(profile: Profile) -> FakeQueryEmbeddingProvider:
        return FakeQueryEmbeddingProvider(model=profile.embedding_profile)

    monkeypatch.setattr(
        "zsper.brain.rag_commands.provider_for_profile",
        provider_for_profile,
    )


SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services" / "brain-api"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


@dataclass(frozen=True)
class _IndexedFixture:
    profile: Profile
    store: ProfileRagStore
    bm25_index: ProfileBm25Index
    vector_index: ProfileVectorIndex
    rag_db_path: Path
    bm25_db_path: Path
    vector_db_path: Path
    document: Document
    exact_chunk: DocumentChunk
    semantic_chunk: DocumentChunk
    unrelated_chunk: DocumentChunk


class _StaticQueryEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str,
        vectors_by_text: dict[str, Sequence[float]],
    ) -> None:
        self.model = model
        self._vectors_by_text = vectors_by_text

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(
            tuple(float(value) for value in self._vectors_by_text[text])
            for text in texts
        )


class _BrokenVectorIndex:
    database_path: Path | None = None

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        del args, kwargs
        raise VectorIndexError("dense index unavailable")


def _hybrid_api() -> tuple[Any, Any]:
    try:
        from zsper.rag import HybridSearchEngine, HybridSearchResult
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"hybrid search API is missing: {exc}")
    return HybridSearchEngine, HybridSearchResult


def _document(profile: Profile, parsed_path: Path) -> Document:
    return Document(
        id="doc-hybrid",
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(parsed_path.with_suffix(".raw")),
        parsed_representation_path=str(parsed_path),
        title="Hybrid Search Fixture",
        metadata={
            "original_path": str(parsed_path.with_suffix(".source")),
            "source_name": parsed_path.name,
        },
        content_hash=f"sha256:{profile.name}:doc-hybrid",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(
    profile: Profile,
    *,
    document_id: str,
    chunk_id: str,
    chunk_index: int,
    text: str,
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        citation_anchor_id=f"anchor-{chunk_id}",
        token_estimate=max(1, len(text.split())),
        byte_start=chunk_index * 100,
        byte_end=chunk_index * 100 + len(text.encode("utf-8")),
        embedding_model=profile.embedding_profile,
        embedding_vector_id=f"vec-{profile.name}-{chunk_id}",
    )


def _anchor(document: Document, chunk: DocumentChunk, source: str) -> CitationAnchor:
    return CitationAnchor(
        id=chunk.citation_anchor_id,
        document_id=document.id,
        chunk_id=chunk.id,
        label=f"{document.title} chunk {chunk.chunk_index + 1}",
        source_path_or_url=source,
        display_range=f"bytes {chunk.byte_start}-{chunk.byte_end}",
    )


def _indexed_fixture(
    tmp_path: Path,
    profile: Profile,
    *,
    use_profile_index_paths: bool = False,
    vector_dimensions: int = 3,
) -> _IndexedFixture:
    if use_profile_index_paths:
        index_root = Path(profile.root) / "brain" / "indexes"
        rag_db_path = index_root / "rag.sqlite"
        bm25_db_path = index_root / "bm25.sqlite"
        vector_db_path = index_root / "vectors.sqlite"
    else:
        rag_db_path = tmp_path / f"{profile.name}-rag.sqlite"
        bm25_db_path = tmp_path / f"{profile.name}-bm25.sqlite"
        vector_db_path = tmp_path / f"{profile.name}-vectors.sqlite"
    store = ProfileRagStore.sqlite(rag_db_path)
    bm25_index = ProfileBm25Index.sqlite(bm25_db_path)
    vector_index = ProfileVectorIndex.sqlite(vector_db_path)
    parsed_path = Path(profile.root) / "brain" / "parsed" / "hybrid.txt"
    source_path = str(parsed_path.with_suffix(".source"))
    document = _document(profile, parsed_path)
    exact_chunk = _chunk(
        profile,
        document_id=document.id,
        chunk_id="chunk-exact",
        chunk_index=0,
        text=(
            "The worker failed with ModuleNotFoundError: No module named "
            "'zsper.rag.indexes.bm25' while loading the exact retrieval index."
        ),
    )
    semantic_chunk = _chunk(
        profile,
        document_id=document.id,
        chunk_id="chunk-semantic",
        chunk_index=1,
        text=(
            "Citation anchors preserve source ranges for grounded answers and "
            "document inspection."
        ),
    )
    unrelated_chunk = _chunk(
        profile,
        document_id=document.id,
        chunk_id="chunk-unrelated",
        chunk_index=2,
        text="The orchestrator records tmux task state for agent runs.",
    )
    chunks = (exact_chunk, semantic_chunk, unrelated_chunk)

    store.upsert_document(profile, document)
    for chunk in chunks:
        store.upsert_chunk(profile, chunk)
        store.upsert_citation_anchor(profile, _anchor(document, chunk, source_path))
    bm25_index.index_chunks(profile, document, chunks)
    vector_index.index_chunks(
        profile,
        document,
        chunks,
        vectors_by_chunk_id={
            exact_chunk.id: _axis_vector(vector_dimensions, 2),
            semantic_chunk.id: _axis_vector(vector_dimensions, 0),
            unrelated_chunk.id: _axis_vector(vector_dimensions, 1),
        },
    )
    return _IndexedFixture(
        profile=profile,
        store=store,
        bm25_index=bm25_index,
        vector_index=vector_index,
        rag_db_path=rag_db_path,
        bm25_db_path=bm25_db_path,
        vector_db_path=vector_db_path,
        document=document,
        exact_chunk=exact_chunk,
        semantic_chunk=semantic_chunk,
        unrelated_chunk=unrelated_chunk,
    )


def _axis_vector(dimensions: int, active_index: int) -> tuple[float, ...]:
    values = [0.0] * dimensions
    values[active_index] = 1.0
    return tuple(values)


def _service_env(
    fixture: _IndexedFixture,
    registry_path: Path,
) -> dict[str, str]:
    profile = fixture.profile
    return {
        "ZSPER_PROFILE_ID": profile.name,
        "ZSPER_PROFILE_ROOT": profile.root,
        "ZSPER_PROFILE_REGISTRY": str(registry_path),
        "ZSPER_RAG_SQLITE_PATH": str(fixture.rag_db_path),
        "ZSPER_BM25_SQLITE_PATH": str(fixture.bm25_db_path),
        "ZSPER_VECTOR_SQLITE_PATH": str(fixture.vector_db_path),
        "POSTGRES_DB": profile.database_name,
        "POSTGRES_DSN": f"postgresql://zsper:local@127.0.0.1/{profile.database_name}",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_KEY_PREFIX": f"zsper:{profile.name}:",
        "ZSPER_MODEL_BASE_URL": "http://127.0.0.1:9127/v1",
    }


def test_hybrid_search_regression_uses_bm25_for_exact_matches(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    HybridSearchEngine, HybridSearchResult = _hybrid_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    fixture = _indexed_fixture(tmp_path, profile)
    engine = HybridSearchEngine(
        store=fixture.store,
        bm25_index=fixture.bm25_index,
        vector_index=fixture.vector_index,
    )

    results = engine.search(
        profile,
        "ModuleNotFoundError: No module named zsper.rag.indexes.bm25",
        query_vector=(0.0, 1.0, 0.0),
        limit=3,
    )

    assert results
    assert isinstance(results[0], HybridSearchResult)
    assert results[0].chunk_id == fixture.exact_chunk.id
    assert results[0].document_id == fixture.document.id
    assert results[0].citation_anchor_id == fixture.exact_chunk.citation_anchor_id
    assert results[0].source_path_or_url.endswith("hybrid.source")
    assert results[0].score_components["bm25"] > 0.0
    assert "dense" in results[0].score_components
    assert "ModuleNotFoundError" in results[0].text_preview


def test_hybrid_search_returns_dense_semantic_matches_with_component_scores(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    HybridSearchEngine, _ = _hybrid_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    fixture = _indexed_fixture(tmp_path, profile)
    engine = HybridSearchEngine(
        store=fixture.store,
        bm25_index=fixture.bm25_index,
        vector_index=fixture.vector_index,
    )

    results = engine.search(
        profile,
        "provenance locator",
        query_vector=(1.0, 0.0, 0.0),
        limit=2,
    )

    assert [result.chunk_id for result in results][:1] == [fixture.semantic_chunk.id]
    result = results[0]
    assert result.profile_id == profile.name
    assert result.citation_anchor_id == fixture.semantic_chunk.citation_anchor_id
    assert result.score_components["bm25"] == 0.0
    assert result.score_components["dense"] > 0.0
    assert result.text_preview == fixture.semantic_chunk.text


def test_hybrid_search_reports_dense_index_errors_when_dense_query_requested(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    HybridSearchEngine, _ = _hybrid_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    fixture = _indexed_fixture(tmp_path, profile)
    engine = HybridSearchEngine(
        store=fixture.store,
        bm25_index=fixture.bm25_index,
        vector_index=_BrokenVectorIndex(),
        query_embedding_provider=_StaticQueryEmbeddingProvider(
            model=profile.embedding_profile,
            vectors_by_text={"semantic source locator": (1.0, 0.0, 0.0)},
        ),
    )

    with pytest.raises(HybridSearchError, match="dense vector search failed"):
        engine.search(profile, "semantic source locator", limit=2)


def test_search_api_route_delegates_to_hybrid_search(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from app.deps import get_query_embedding_provider
    from app.main import create_app

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    fixture = _indexed_fixture(tmp_path, profile)
    app = create_app(environ=_service_env(fixture, isolated_registry_path))
    app.dependency_overrides[get_query_embedding_provider] = lambda: (
        _StaticQueryEmbeddingProvider(
            model=profile.embedding_profile,
            vectors_by_text={"semantic source locator": (1.0, 0.0, 0.0)},
        )
    )
    client = TestClient(app)

    response = client.get(
        "/api/search",
        params={"query": "semantic source locator", "limit": 2},
        headers={"X-Zsper-Profile-Id": "work"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "work"
    assert body["query"] == "semantic source locator"
    assert body["results"][0]["chunk_id"] == fixture.semantic_chunk.id
    assert body["results"][0]["citation_anchor_id"] == (
        fixture.semantic_chunk.citation_anchor_id
    )
    assert body["results"][0]["source_path_or_url"].endswith("hybrid.source")
    assert set(body["results"][0]["score_components"]) >= {"bm25", "dense"}


def test_search_api_uses_profile_local_sqlite_rag_store_for_air_default_paths(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from app.deps import get_query_embedding_provider
    from app.main import create_app

    profile = initialize_profile(
        mode="air",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
    )
    fixture = _indexed_fixture(
        tmp_path,
        profile,
        use_profile_index_paths=True,
    )
    env = _service_env(fixture, isolated_registry_path)
    env.pop("ZSPER_RAG_SQLITE_PATH")
    env.pop("ZSPER_BM25_SQLITE_PATH")
    env.pop("ZSPER_VECTOR_SQLITE_PATH")
    app = create_app(environ=env)
    app.dependency_overrides[get_query_embedding_provider] = lambda: (
        _StaticQueryEmbeddingProvider(
            model=profile.embedding_profile,
            vectors_by_text={"semantic source locator": (1.0, 0.0, 0.0)},
        )
    )
    client = TestClient(app)

    response = client.get(
        "/api/search",
        params={"query": "semantic source locator", "limit": 2},
        headers={"X-Zsper-Profile-Id": "air"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "air"
    assert body["results"][0]["chunk_id"] == fixture.semantic_chunk.id
    assert body["results"][0]["citation_anchor_id"] == (
        fixture.semantic_chunk.citation_anchor_id
    )
    assert body["results"][0]["source_path_or_url"].endswith("hybrid.source")
    assert body["results"][0]["score_components"]["dense"] > 0.0


def test_cli_brain_search_uses_hybrid_index_for_resolved_profiles(
    tmp_path: Path,
    isolated_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from zsper.cli import app

    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    fixture = _indexed_fixture(tmp_path, profile, vector_dimensions=384)
    monkeypatch.setenv("ZSPER_RAG_SQLITE_PATH", str(fixture.rag_db_path))
    monkeypatch.setenv("ZSPER_BM25_SQLITE_PATH", str(fixture.bm25_db_path))
    monkeypatch.setenv("ZSPER_VECTOR_SQLITE_PATH", str(fixture.vector_db_path))

    exit_code = app(
        [
            "brain",
            "search",
            "ModuleNotFoundError",
            "zsper.rag.indexes.bm25",
            "--profile",
            "work",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert fixture.exact_chunk.id in captured.out
    assert fixture.exact_chunk.citation_anchor_id in captured.out
    assert "ModuleNotFoundError" in captured.out


def test_cli_brain_search_uses_hybrid_index_for_air_profile_default_paths(
    tmp_path: Path,
    isolated_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from zsper.cli import app

    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    monkeypatch.delenv("ZSPER_RAG_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_BM25_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_VECTOR_SQLITE_PATH", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    profile = initialize_profile(
        mode="air",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
    )
    fixture = _indexed_fixture(
        tmp_path,
        profile,
        use_profile_index_paths=True,
        vector_dimensions=384,
    )

    exit_code = app(
        [
            "brain",
            "search",
            "ModuleNotFoundError",
            "zsper.rag.indexes.bm25",
            "--profile",
            "air",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert fixture.exact_chunk.id in captured.out
    assert fixture.exact_chunk.citation_anchor_id in captured.out
    assert "hybrid.source" in captured.out
    assert "bm25=" in captured.out
    assert "dense=" in captured.out
    assert "ModuleNotFoundError" in captured.out
