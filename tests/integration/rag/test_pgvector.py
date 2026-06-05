from __future__ import annotations

import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag.models import Document, DocumentChunk


def _vector_api() -> tuple[Any, Any]:
    try:
        from zsper.rag.indexes import ProfileVectorIndex, VectorSearchResult
    except ModuleNotFoundError as exc:
        pytest.fail(f"Vector index API is missing: {exc}")
    return ProfileVectorIndex, VectorSearchResult


def _document(profile: Profile, document_id: str = "doc-pgvector") -> Document:
    source_path = Path(profile.root) / "brain" / "documents" / f"{document_id}.md"
    return Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(source_path),
        parsed_representation_path=str(source_path.with_suffix(".txt")),
        title=f"{profile.name} pgvector fixture",
        metadata={"source_name": source_path.name},
        content_hash=f"sha256:{profile.name}-{document_id}",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(
    profile: Profile,
    document_id: str,
    chunk_id: str,
    text: str,
    *,
    chunk_index: int = 0,
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


class _FakePostgresConnectionFactory:
    def __init__(self) -> None:
        self.connection = _FakePostgresConnection()

    @property
    def executed(self) -> list[tuple[str, tuple[Any, ...]]]:
        return self.connection.executed

    def __call__(self) -> "_FakePostgresConnection":
        return self.connection


class _FakePostgresConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

    def __enter__(self) -> "_FakePostgresConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> "_FakePostgresCursor":
        return _FakePostgresCursor(self)


class _FakePostgresCursor:
    def __init__(self, connection: _FakePostgresConnection) -> None:
        self.connection = connection
        self._rows: list[dict[str, Any]] = []

    def __enter__(self) -> "_FakePostgresCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | None = None,
    ) -> "_FakePostgresCursor":
        bound_params = tuple(params or ())
        self.connection.executed.append((sql, bound_params))
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert into rag_chunk_vectors"):
            self._upsert_vector(bound_params)
        elif "from rag_chunk_vectors" in normalized and "<=>" in normalized:
            self._search_vectors(bound_params)
        else:
            self._rows = []
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def _upsert_vector(self, params: tuple[Any, ...]) -> None:
        profile_id, document_id, chunk_id, model, vector_id, vector_literal = params
        self.connection.rows[(profile_id, vector_id)] = {
            "profile_id": profile_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "embedding_model": model,
            "embedding_vector_id": vector_id,
            "vector": _parse_pgvector_literal(vector_literal),
        }

    def _search_vectors(self, params: tuple[Any, ...]) -> None:
        query_vector = _parse_pgvector_literal(params[0])
        profile_id = params[1]
        embedding_model = params[2]
        limit = params[4]
        rows = [
            {
                **row,
                "score": _cosine_similarity(query_vector, row["vector"]),
            }
            for row in self.connection.rows.values()
            if row["profile_id"] == profile_id
            and row["embedding_model"] == embedding_model
        ]
        rows.sort(key=lambda row: (-row["score"], row["document_id"], row["chunk_id"]))
        self._rows = rows[:limit]


def test_postgres_vector_index_uses_pgvector_and_profile_scope(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileVectorIndex, VectorSearchResult = _vector_api()
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    personal = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    work_document = _document(work)
    personal_document = _document(personal)
    work_chunk = _chunk(
        work,
        work_document.id,
        "chunk-relevant",
        "Dense pgvector retrieval should find this work chunk.",
    )
    personal_chunk = _chunk(
        personal,
        personal_document.id,
        "chunk-relevant",
        "This personal chunk has a similar id but must stay isolated.",
    )
    connection_factory = _FakePostgresConnectionFactory()
    index = ProfileVectorIndex.postgres(connection_factory)

    index.index_chunks(
        work,
        work_document,
        [work_chunk],
        vectors_by_chunk_id={work_chunk.id: (1.0, 0.0, 0.0)},
    )
    index.index_chunks(
        personal,
        personal_document,
        [personal_chunk],
        vectors_by_chunk_id={personal_chunk.id: (0.0, 1.0, 0.0)},
    )
    results = index.search(
        work,
        query_vector=(0.97, 0.03, 0.0),
        embedding_model=work.embedding_profile,
    )

    assert results
    assert isinstance(results[0], VectorSearchResult)
    assert [(result.profile_id, result.chunk_id) for result in results] == [
        (work.name, work_chunk.id)
    ]
    assert any(
        "CREATE EXTENSION IF NOT EXISTS vector" in sql
        for sql, _ in connection_factory.executed
    )
    assert any("embedding vector(384)" in sql for sql, _ in connection_factory.executed)
    assert any(
        "USING hnsw (embedding vector_cosine_ops)" in sql
        for sql, _ in connection_factory.executed
    )
    search_sql = next(
        sql for sql, _ in connection_factory.executed if "FROM rag_chunk_vectors" in sql
    )
    assert "<=>" in search_sql
    assert "WHERE profile_id = %s AND embedding_model = %s" in " ".join(search_sql.split())


@pytest.mark.integration
def test_live_pgvector_round_trip_when_dsn_is_configured(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    dsn = os.environ.get("ZSPER_TEST_PGVECTOR_DSN")
    if not dsn:
        pytest.skip("set ZSPER_TEST_PGVECTOR_DSN to run the live pgvector smoke test")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        pytest.skip(f"psycopg is not installed: {exc}")

    ProfileVectorIndex, _ = _vector_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work-live",
        registry_path=isolated_registry_path,
    )
    document = _document(profile, document_id="doc-live-pgvector")
    irrelevant = _chunk(
        profile,
        document.id,
        "chunk-live-irrelevant",
        "Unrelated live pgvector row.",
        chunk_index=0,
    )
    relevant = _chunk(
        profile,
        document.id,
        "chunk-live-relevant",
        "Relevant live pgvector row.",
        chunk_index=1,
    )

    def _connect() -> Any:
        return psycopg.connect(dsn)

    try:
        index = ProfileVectorIndex.postgres(_connect)
    except Exception as exc:
        pytest.skip(f"pgvector is unavailable for live smoke test: {exc}")

    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rag_chunk_vectors WHERE profile_id = %s", (profile.name,))

    index.index_chunks(
        profile,
        document,
        [irrelevant, relevant],
        vectors_by_chunk_id={
            irrelevant.id: _unit_vector(384, 1),
            relevant.id: _unit_vector(384, 0),
        },
    )
    results = index.search(
        profile,
        query_vector=_unit_vector(384, 0),
        embedding_model=profile.embedding_profile,
        limit=1,
    )

    assert [result.chunk_id for result in results] == [relevant.id]


def _parse_pgvector_literal(value: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in value.strip("[]").split(","))


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(left * right for left, right in zip(a, b, strict=True))
    a_norm = math.sqrt(sum(value * value for value in a))
    b_norm = math.sqrt(sum(value * value for value in b))
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return dot / (a_norm * b_norm)


def _unit_vector(dimensions: int, hot_index: int) -> tuple[float, ...]:
    return tuple(1.0 if index == hot_index else 0.0 for index in range(dimensions))
