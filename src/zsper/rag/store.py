"""Profile-scoped RAG document persistence."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from zsper.brain.ledgers import LedgerKind, append_ledger_record, read_ledger_records
from zsper.profiles import Profile
from zsper.rag.models import CitationAnchor, Document, DocumentChunk
from zsper.rag.schema import POSTGRES_RAG_SCHEMA_SQL, SQLITE_RAG_SCHEMA_SQL


class RagStoreError(ValueError):
    """Raised when a RAG store operation is invalid."""


ConnectionFactory = Callable[[], Any]
StoreBackend = Literal["sqlite", "postgres"]

_DOCUMENT_COLUMNS = (
    "id",
    "profile_id",
    "source_type",
    "raw_asset_path",
    "parsed_representation_path",
    "title",
    "metadata_json",
    "content_hash",
    "parser",
    "created_at",
    "updated_at",
)
_CHUNK_COLUMNS = (
    "id",
    "document_id",
    "chunk_index",
    "text",
    "citation_anchor_id",
    "token_estimate",
    "byte_start",
    "byte_end",
    "embedding_model",
    "embedding_vector_id",
)
_CITATION_ANCHOR_COLUMNS = (
    "id",
    "document_id",
    "chunk_id",
    "label",
    "source_path_or_url",
    "display_range",
)


@dataclass(frozen=True)
class ProfileRagStore:
    database_path: Path | None
    backend: StoreBackend = "sqlite"
    connection_factory: ConnectionFactory | None = None

    @classmethod
    def sqlite(cls, database_path: str | Path) -> "ProfileRagStore":
        store = cls(
            database_path=Path(database_path).expanduser().resolve(strict=False),
            backend="sqlite",
        )
        store.initialize()
        return store

    @classmethod
    def postgres(cls, connection_factory: ConnectionFactory) -> "ProfileRagStore":
        store = cls(
            database_path=None,
            backend="postgres",
            connection_factory=connection_factory,
        )
        store.initialize()
        return store

    @classmethod
    def postgres_dsn(
        cls,
        dsn: str,
        **connect_kwargs: Any,
    ) -> "ProfileRagStore":
        if not isinstance(dsn, str) or not dsn.strip():
            raise RagStoreError("Postgres DSN must be a non-empty string")

        def _connect() -> Any:
            try:
                import psycopg  # type: ignore[import-not-found]
            except ModuleNotFoundError as exc:  # pragma: no cover - env dependent.
                raise RagStoreError(
                    "psycopg is required to create a Postgres RAG store from a DSN"
                ) from exc
            return psycopg.connect(dsn, **connect_kwargs)

        return cls.postgres(_connect)

    def initialize(self) -> None:
        if self.backend == "sqlite":
            database_path = self._require_sqlite_path()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(SQLITE_RAG_SCHEMA_SQL)
            return
        if self.backend == "postgres":
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    for statement in _postgres_schema_statements():
                        cursor.execute(statement)
            return
        raise RagStoreError(f"unsupported RAG store backend: {self.backend}")

    def upsert_document(self, profile: Profile, document: Document) -> None:
        if document.profile_id != profile.name:
            raise RagStoreError(
                "document profile_id must match the profile used for the store operation"
            )
        params = (
            profile.name,
            document.id,
            document.source_type,
            document.raw_asset_path,
            document.parsed_representation_path,
            document.title,
            _json_dump(document.metadata),
            document.content_hash,
            document.parser,
            document.created_at,
            document.updated_at,
        )
        if self.backend == "sqlite":
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO documents (
                      profile_id,
                      id,
                      source_type,
                      raw_asset_path,
                      parsed_representation_path,
                      title,
                      metadata_json,
                      content_hash,
                      parser,
                      created_at,
                      updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id, id) DO UPDATE SET
                      source_type = excluded.source_type,
                      raw_asset_path = excluded.raw_asset_path,
                      parsed_representation_path = excluded.parsed_representation_path,
                      title = excluded.title,
                      metadata_json = excluded.metadata_json,
                      content_hash = excluded.content_hash,
                      parser = excluded.parser,
                      created_at = excluded.created_at,
                      updated_at = excluded.updated_at
                    """,
                    params,
                )
        elif self.backend == "postgres":
            self._postgres_execute(
                """
                INSERT INTO documents (
                  profile_id,
                  id,
                  source_type,
                  raw_asset_path,
                  parsed_representation_path,
                  title,
                  metadata,
                  content_hash,
                  parser,
                  created_at,
                  updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT(profile_id, id) DO UPDATE SET
                  source_type = excluded.source_type,
                  raw_asset_path = excluded.raw_asset_path,
                  parsed_representation_path = excluded.parsed_representation_path,
                  title = excluded.title,
                  metadata = excluded.metadata,
                  content_hash = excluded.content_hash,
                  parser = excluded.parser,
                  created_at = excluded.created_at,
                  updated_at = excluded.updated_at
                """,
                params,
            )
        else:
            raise RagStoreError(f"unsupported RAG store backend: {self.backend}")
        append_ledger_record(
            profile,
            LedgerKind.DOCUMENTS,
            record_id=document.id,
            payload={
                "event": "document.upserted",
                "schema": "rag.document.v1",
                "document": document.to_dict(),
            },
        )

    def upsert_chunk(self, profile: Profile, chunk: DocumentChunk) -> None:
        self._require_document(profile, chunk.document_id)
        params = (
            profile.name,
            chunk.id,
            chunk.document_id,
            chunk.chunk_index,
            chunk.text,
            chunk.citation_anchor_id,
            chunk.token_estimate,
            chunk.byte_start,
            chunk.byte_end,
            chunk.embedding_model,
            chunk.embedding_vector_id,
        )
        if self.backend == "postgres":
            self._postgres_execute(
                """
                INSERT INTO document_chunks (
                  profile_id,
                  id,
                  document_id,
                  chunk_index,
                  text,
                  citation_anchor_id,
                  token_estimate,
                  byte_start,
                  byte_end,
                  embedding_model,
                  embedding_vector_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(profile_id, id) DO UPDATE SET
                  document_id = excluded.document_id,
                  chunk_index = excluded.chunk_index,
                  text = excluded.text,
                  citation_anchor_id = excluded.citation_anchor_id,
                  token_estimate = excluded.token_estimate,
                  byte_start = excluded.byte_start,
                  byte_end = excluded.byte_end,
                  embedding_model = excluded.embedding_model,
                  embedding_vector_id = excluded.embedding_vector_id
                """,
                params,
            )
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO document_chunks (
                      profile_id,
                      id,
                      document_id,
                      chunk_index,
                      text,
                      citation_anchor_id,
                      token_estimate,
                      byte_start,
                      byte_end,
                      embedding_model,
                      embedding_vector_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id, id) DO UPDATE SET
                      document_id = excluded.document_id,
                      chunk_index = excluded.chunk_index,
                      text = excluded.text,
                      citation_anchor_id = excluded.citation_anchor_id,
                      token_estimate = excluded.token_estimate,
                      byte_start = excluded.byte_start,
                      byte_end = excluded.byte_end,
                      embedding_model = excluded.embedding_model,
                      embedding_vector_id = excluded.embedding_vector_id
                    """,
                    params,
                )
        except sqlite3.IntegrityError as exc:
            raise RagStoreError(str(exc)) from exc

    def upsert_citation_anchor(self, profile: Profile, anchor: CitationAnchor) -> None:
        self._require_document(profile, anchor.document_id)
        params = (
            profile.name,
            anchor.id,
            anchor.document_id,
            anchor.chunk_id,
            anchor.label,
            anchor.source_path_or_url,
            anchor.display_range,
        )
        if self.backend == "postgres":
            self._postgres_execute(
                """
                INSERT INTO citation_anchors (
                  profile_id,
                  id,
                  document_id,
                  chunk_id,
                  label,
                  source_path_or_url,
                  display_range
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(profile_id, id) DO UPDATE SET
                  document_id = excluded.document_id,
                  chunk_id = excluded.chunk_id,
                  label = excluded.label,
                  source_path_or_url = excluded.source_path_or_url,
                  display_range = excluded.display_range
                """,
                params,
            )
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO citation_anchors (
                      profile_id,
                      id,
                      document_id,
                      chunk_id,
                      label,
                      source_path_or_url,
                      display_range
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id, id) DO UPDATE SET
                      document_id = excluded.document_id,
                      chunk_id = excluded.chunk_id,
                      label = excluded.label,
                      source_path_or_url = excluded.source_path_or_url,
                      display_range = excluded.display_range
                    """,
                    params,
                )
        except sqlite3.IntegrityError as exc:
            raise RagStoreError(str(exc)) from exc

    def get_document(self, profile: Profile, document_id: str) -> Document | None:
        if self.backend == "postgres":
            row = self._postgres_fetchone(
                """
                SELECT
                  id,
                  profile_id,
                  source_type,
                  raw_asset_path,
                  parsed_representation_path,
                  title,
                  metadata::text AS metadata_json,
                  content_hash,
                  parser,
                  created_at::text AS created_at,
                  updated_at::text AS updated_at
                FROM documents
                WHERE profile_id = %s AND id = %s
                """,
                (profile.name, document_id),
                _DOCUMENT_COLUMNS,
            )
            if row is None:
                return None
            return _document_from_row(row)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM documents
                WHERE profile_id = ? AND id = ?
                """,
                (profile.name, document_id),
            ).fetchone()
        if row is None:
            return None
        return _document_from_row(row)

    def list_documents(self, profile: Profile) -> list[Document]:
        if self.backend == "postgres":
            rows = self._postgres_fetchall(
                """
                SELECT
                  id,
                  profile_id,
                  source_type,
                  raw_asset_path,
                  parsed_representation_path,
                  title,
                  metadata::text AS metadata_json,
                  content_hash,
                  parser,
                  created_at::text AS created_at,
                  updated_at::text AS updated_at
                FROM documents
                WHERE profile_id = %s
                ORDER BY created_at, id
                """,
                (profile.name,),
                _DOCUMENT_COLUMNS,
            )
            return [_document_from_row(row) for row in rows]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM documents
                WHERE profile_id = ?
                ORDER BY created_at, id
                """,
                (profile.name,),
            ).fetchall()
        return [_document_from_row(row) for row in rows]

    def list_chunks(self, profile: Profile, document_id: str) -> list[DocumentChunk]:
        if self.backend == "postgres":
            rows = self._postgres_fetchall(
                """
                SELECT
                  id,
                  document_id,
                  chunk_index,
                  text,
                  citation_anchor_id,
                  token_estimate,
                  byte_start,
                  byte_end,
                  embedding_model,
                  embedding_vector_id
                FROM document_chunks
                WHERE profile_id = %s AND document_id = %s
                ORDER BY chunk_index, id
                """,
                (profile.name, document_id),
                _CHUNK_COLUMNS,
            )
            return [_chunk_from_row(row) for row in rows]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM document_chunks
                WHERE profile_id = ? AND document_id = ?
                ORDER BY chunk_index, id
                """,
                (profile.name, document_id),
            ).fetchall()
        return [_chunk_from_row(row) for row in rows]

    def list_citation_anchors(
        self,
        profile: Profile,
        document_id: str,
    ) -> list[CitationAnchor]:
        if self.backend == "postgres":
            rows = self._postgres_fetchall(
                """
                SELECT
                  id,
                  document_id,
                  chunk_id,
                  label,
                  source_path_or_url,
                  display_range
                FROM citation_anchors
                WHERE profile_id = %s AND document_id = %s
                ORDER BY id
                """,
                (profile.name, document_id),
                _CITATION_ANCHOR_COLUMNS,
            )
            return [_citation_anchor_from_row(row) for row in rows]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM citation_anchors
                WHERE profile_id = ? AND document_id = ?
                ORDER BY id
                """,
                (profile.name, document_id),
            ).fetchall()
        return [_citation_anchor_from_row(row) for row in rows]

    def _connect(self) -> Any:
        if self.backend == "sqlite":
            conn = sqlite3.connect(self._require_sqlite_path())
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        if self.backend == "postgres":
            if self.connection_factory is None:
                raise RagStoreError("Postgres RAG store requires a connection factory")
            return self.connection_factory()
        raise RagStoreError(f"unsupported RAG store backend: {self.backend}")

    def _require_sqlite_path(self) -> Path:
        if self.database_path is None:
            raise RagStoreError("SQLite RAG store requires a database path")
        return self.database_path

    def _postgres_execute(self, sql: str, params: Sequence[Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))

    def _postgres_fetchone(
        self,
        sql: str,
        params: Sequence[Any],
        columns: Sequence[str],
    ) -> Mapping[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_mapping(row, columns)

    def _postgres_fetchall(
        self,
        sql: str,
        params: Sequence[Any],
        columns: Sequence[str],
    ) -> list[Mapping[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
        return [_row_to_mapping(row, columns) for row in rows]

    def _require_document(self, profile: Profile, document_id: str) -> None:
        if self.get_document(profile, document_id) is None:
            raise RagStoreError(
                f"document does not exist for profile {profile.name}: {document_id}"
            )


def replay_document_metadata(profile: Profile) -> dict[str, Document]:
    documents: dict[str, Document] = {}
    for row in read_ledger_records(profile, LedgerKind.DOCUMENTS):
        payload = row.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if payload.get("event") != "document.upserted":
            continue
        document_data = payload.get("document")
        if not isinstance(document_data, dict):
            continue
        document = Document.from_dict(document_data)
        if document.profile_id == profile.name:
            documents[document.id] = document
    return documents


def _json_dump(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _json_load(value: str) -> dict[str, Any]:
    data = json.loads(value)
    if not isinstance(data, dict):
        raise RagStoreError("stored document metadata must be a JSON object")
    return data


def _postgres_schema_statements() -> tuple[str, ...]:
    return tuple(
        statement.strip()
        for statement in POSTGRES_RAG_SCHEMA_SQL.split(";")
        if statement.strip()
    )


def _row_to_mapping(row: Any, columns: Sequence[str]) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    try:
        return {column: row[column] for column in columns}
    except (IndexError, KeyError, TypeError):
        return dict(zip(columns, row, strict=True))


def _document_from_row(row: Mapping[str, Any] | sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        profile_id=row["profile_id"],
        source_type=row["source_type"],
        raw_asset_path=row["raw_asset_path"],
        parsed_representation_path=row["parsed_representation_path"],
        title=row["title"],
        metadata=_json_load(row["metadata_json"]),
        content_hash=row["content_hash"],
        parser=row["parser"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _chunk_from_row(row: Mapping[str, Any] | sqlite3.Row) -> DocumentChunk:
    return DocumentChunk(
        id=row["id"],
        document_id=row["document_id"],
        chunk_index=row["chunk_index"],
        text=row["text"],
        citation_anchor_id=row["citation_anchor_id"],
        token_estimate=row["token_estimate"],
        byte_start=row["byte_start"],
        byte_end=row["byte_end"],
        embedding_model=row["embedding_model"],
        embedding_vector_id=row["embedding_vector_id"],
    )


def _citation_anchor_from_row(row: Mapping[str, Any] | sqlite3.Row) -> CitationAnchor:
    return CitationAnchor(
        id=row["id"],
        document_id=row["document_id"],
        chunk_id=row["chunk_id"],
        label=row["label"],
        source_path_or_url=row["source_path_or_url"],
        display_range=row["display_range"],
    )
