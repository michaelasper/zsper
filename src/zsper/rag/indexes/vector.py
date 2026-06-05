"""Profile-scoped dense vector index for RAG chunks."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from zsper.profiles import Profile
from zsper.rag.models import Document, DocumentChunk


VECTOR_DIMENSIONS: Final[int] = 384

SQLITE_VECTOR_SCHEMA_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS rag_chunk_vectors (
  profile_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_vector_id TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  PRIMARY KEY (profile_id, document_id, chunk_id, embedding_model),
  UNIQUE (profile_id, embedding_vector_id)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunk_vectors_profile_model
  ON rag_chunk_vectors (profile_id, embedding_model);
"""

POSTGRES_VECTOR_SCHEMA_SQL: Final[str] = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunk_vectors (
  profile_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_vector_id TEXT NOT NULL,
  embedding vector({VECTOR_DIMENSIONS}) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, document_id, chunk_id, embedding_model),
  UNIQUE (profile_id, embedding_vector_id)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunk_vectors_profile_model
  ON rag_chunk_vectors (profile_id, embedding_model);
CREATE INDEX IF NOT EXISTS idx_rag_chunk_vectors_embedding
  ON rag_chunk_vectors USING hnsw (embedding vector_cosine_ops);
"""


class VectorIndexError(ValueError):
    """Raised when a vector index operation is invalid."""


ConnectionFactory = Callable[[], Any]
VectorBackend = Literal["sqlite", "postgres"]

_RESULT_COLUMNS = (
    "profile_id",
    "document_id",
    "chunk_id",
    "embedding_model",
    "embedding_vector_id",
    "score",
)


@dataclass(frozen=True)
class VectorSearchResult:
    profile_id: str
    document_id: str
    chunk_id: str
    embedding_model: str
    embedding_vector_id: str
    score: float


@dataclass(frozen=True)
class ProfileVectorIndex:
    database_path: Path | None
    backend: VectorBackend = "sqlite"
    connection_factory: ConnectionFactory | None = None

    @classmethod
    def sqlite(cls, database_path: str | Path) -> "ProfileVectorIndex":
        index = cls(
            database_path=Path(database_path).expanduser().resolve(strict=False),
            backend="sqlite",
        )
        index.initialize()
        return index

    @classmethod
    def postgres(cls, connection_factory: ConnectionFactory) -> "ProfileVectorIndex":
        index = cls(
            database_path=None,
            backend="postgres",
            connection_factory=connection_factory,
        )
        index.initialize()
        return index

    @classmethod
    def postgres_dsn(
        cls,
        dsn: str,
        **connect_kwargs: Any,
    ) -> "ProfileVectorIndex":
        if not isinstance(dsn, str) or not dsn.strip():
            raise VectorIndexError("Postgres DSN must be a non-empty string")

        def _connect() -> Any:
            try:
                import psycopg  # type: ignore[import-not-found]
            except ModuleNotFoundError as exc:  # pragma: no cover - env dependent.
                raise VectorIndexError(
                    "psycopg is required to create a Postgres vector index from a DSN"
                ) from exc
            return psycopg.connect(dsn, **connect_kwargs)

        return cls.postgres(_connect)

    def initialize(self) -> None:
        if self.backend == "sqlite":
            database_path = self._require_sqlite_path()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(SQLITE_VECTOR_SCHEMA_SQL)
            return
        if self.backend == "postgres":
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    for statement in _postgres_schema_statements():
                        cursor.execute(statement)
            return
        raise VectorIndexError(f"unsupported vector index backend: {self.backend}")

    def index_chunks(
        self,
        profile: Profile,
        document: Document,
        chunks: Sequence[DocumentChunk],
        *,
        vectors_by_chunk_id: Mapping[str, Sequence[float]],
    ) -> None:
        if document.profile_id != profile.name:
            raise VectorIndexError(
                "document profile_id must match the profile used for indexing"
            )
        rows = [
            _row_for_chunk(
                profile=profile,
                document=document,
                chunk=chunk,
                vector=vectors_by_chunk_id.get(chunk.id),
            )
            for chunk in chunks
        ]
        if self.backend == "sqlite":
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO rag_chunk_vectors (
                      profile_id,
                      document_id,
                      chunk_id,
                      embedding_model,
                      embedding_vector_id,
                      vector_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(
                      profile_id,
                      document_id,
                      chunk_id,
                      embedding_model
                    ) DO UPDATE SET
                      embedding_vector_id = excluded.embedding_vector_id,
                      vector_json = excluded.vector_json
                    """,
                    [
                        (
                            row["profile_id"],
                            row["document_id"],
                            row["chunk_id"],
                            row["embedding_model"],
                            row["embedding_vector_id"],
                            _json_vector(row["vector"]),
                        )
                        for row in rows
                    ],
                )
            return
        if self.backend == "postgres":
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    for row in rows:
                        cursor.execute(
                            """
                            INSERT INTO rag_chunk_vectors (
                              profile_id,
                              document_id,
                              chunk_id,
                              embedding_model,
                              embedding_vector_id,
                              embedding
                            ) VALUES (%s, %s, %s, %s, %s, %s::vector)
                            ON CONFLICT(
                              profile_id,
                              document_id,
                              chunk_id,
                              embedding_model
                            ) DO UPDATE SET
                              embedding_vector_id = excluded.embedding_vector_id,
                              embedding = excluded.embedding,
                              updated_at = now()
                            """,
                            (
                                row["profile_id"],
                                row["document_id"],
                                row["chunk_id"],
                                row["embedding_model"],
                                row["embedding_vector_id"],
                                _pgvector_literal(row["vector"]),
                            ),
                        )
            return
        raise VectorIndexError(f"unsupported vector index backend: {self.backend}")

    def search(
        self,
        profile: Profile,
        *,
        query_vector: Sequence[float],
        embedding_model: str,
        limit: int = 10,
    ) -> list[VectorSearchResult]:
        if limit <= 0:
            return []
        vector = _normalize_vector(query_vector)
        if not isinstance(embedding_model, str) or not embedding_model.strip():
            raise VectorIndexError("embedding_model must be a non-empty string")
        if self.backend == "sqlite":
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                      profile_id,
                      document_id,
                      chunk_id,
                      embedding_model,
                      embedding_vector_id,
                      vector_json
                    FROM rag_chunk_vectors
                    WHERE profile_id = ? AND embedding_model = ?
                    """,
                    (profile.name, embedding_model),
                ).fetchall()
            results = [
                VectorSearchResult(
                    profile_id=row["profile_id"],
                    document_id=row["document_id"],
                    chunk_id=row["chunk_id"],
                    embedding_model=row["embedding_model"],
                    embedding_vector_id=row["embedding_vector_id"],
                    score=_cosine_similarity(vector, _load_vector(row["vector_json"])),
                )
                for row in rows
            ]
            results.sort(
                key=lambda result: (
                    -result.score,
                    result.document_id,
                    result.chunk_id,
                    result.embedding_vector_id,
                )
            )
            return results[:limit]
        if self.backend == "postgres":
            vector_literal = _pgvector_literal(vector)
            rows = self._postgres_fetchall(
                """
                SELECT
                  profile_id,
                  document_id,
                  chunk_id,
                  embedding_model,
                  embedding_vector_id,
                  1 - (embedding <=> %s::vector) AS score
                FROM rag_chunk_vectors
                WHERE profile_id = %s AND embedding_model = %s
                ORDER BY embedding <=> %s::vector ASC, document_id, chunk_id
                LIMIT %s
                """,
                (
                    vector_literal,
                    profile.name,
                    embedding_model,
                    vector_literal,
                    limit,
                ),
            )
            return [
                VectorSearchResult(
                    profile_id=row["profile_id"],
                    document_id=row["document_id"],
                    chunk_id=row["chunk_id"],
                    embedding_model=row["embedding_model"],
                    embedding_vector_id=row["embedding_vector_id"],
                    score=float(row["score"]),
                )
                for row in rows
            ]
        raise VectorIndexError(f"unsupported vector index backend: {self.backend}")

    def _connect(self) -> Any:
        if self.backend == "sqlite":
            conn = sqlite3.connect(self._require_sqlite_path())
            conn.row_factory = sqlite3.Row
            return conn
        if self.backend == "postgres":
            if self.connection_factory is None:
                raise VectorIndexError("Postgres vector index requires a connection factory")
            return self.connection_factory()
        raise VectorIndexError(f"unsupported vector index backend: {self.backend}")

    def _require_sqlite_path(self) -> Path:
        if self.database_path is None:
            raise VectorIndexError("SQLite vector index requires a database path")
        return self.database_path

    def _postgres_fetchall(
        self,
        sql: str,
        params: Sequence[Any],
    ) -> list[Mapping[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        return [_row_to_mapping(row, _RESULT_COLUMNS) for row in rows]


def _row_for_chunk(
    *,
    profile: Profile,
    document: Document,
    chunk: DocumentChunk,
    vector: Sequence[float] | None,
) -> dict[str, Any]:
    if chunk.document_id != document.id:
        raise VectorIndexError(
            "chunk document_id must match the document used for indexing"
        )
    if chunk.embedding_model is None or chunk.embedding_vector_id is None:
        raise VectorIndexError("chunk embedding metadata is required for vector indexing")
    if vector is None:
        raise VectorIndexError(f"missing vector for chunk: {chunk.id}")
    return {
        "profile_id": profile.name,
        "document_id": document.id,
        "chunk_id": chunk.id,
        "embedding_model": chunk.embedding_model,
        "embedding_vector_id": chunk.embedding_vector_id,
        "vector": _normalize_vector(vector),
    }


def _normalize_vector(vector: Sequence[float]) -> tuple[float, ...]:
    if isinstance(vector, (str, bytes)):
        raise VectorIndexError("embedding vector must be a numeric sequence")
    values = tuple(float(value) for value in vector)
    if not values:
        raise VectorIndexError("embedding vector must not be empty")
    if any(not math.isfinite(value) for value in values):
        raise VectorIndexError("embedding vector values must be finite")
    return values


def _json_vector(vector: Sequence[float]) -> str:
    return json.dumps(tuple(vector), separators=(",", ":"))


def _load_vector(value: str) -> tuple[float, ...]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise VectorIndexError("stored embedding vector is invalid JSON") from exc
    if not isinstance(data, list):
        raise VectorIndexError("stored embedding vector must be a JSON list")
    return _normalize_vector(data)


def _pgvector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(_format_float(value) for value in vector) + "]"


def _format_float(value: float) -> str:
    return format(value, ".17g")


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    try:
        dot = sum(left * right for left, right in zip(a, b, strict=True))
    except ValueError as exc:
        raise VectorIndexError("embedding vector dimensions must match") from exc
    a_norm = math.sqrt(sum(value * value for value in a))
    b_norm = math.sqrt(sum(value * value for value in b))
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return dot / (a_norm * b_norm)


def _postgres_schema_statements() -> tuple[str, ...]:
    return tuple(
        statement.strip()
        for statement in POSTGRES_VECTOR_SCHEMA_SQL.split(";")
        if statement.strip()
    )


def _row_to_mapping(row: Any, columns: Sequence[str]) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    try:
        return {column: row[column] for column in columns}
    except (IndexError, KeyError, TypeError):
        return dict(zip(columns, row, strict=True))
