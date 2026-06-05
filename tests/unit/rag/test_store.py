import json
from pathlib import Path
from typing import Any

import pytest

from zsper.profiles import initialize_profile
from zsper.rag import (
    POSTGRES_RAG_SCHEMA_SQL,
    SQLITE_RAG_SCHEMA_SQL,
    CitationAnchor,
    Document,
    DocumentChunk,
    ProfileRagStore,
    RagStoreError,
    replay_document_metadata,
)


def _document(profile_id: str, document_id: str = "doc-1") -> Document:
    return Document(
        id=document_id,
        profile_id=profile_id,
        source_type="file",
        raw_asset_path=f"/profiles/{profile_id}/brain/assets/{document_id}.md",
        parsed_representation_path=f"/profiles/{profile_id}/brain/parsed/{document_id}.txt",
        title=f"{profile_id} document",
        metadata={"source_name": f"{document_id}.md", "page_count": 3},
        content_hash=f"sha256:{profile_id}-{document_id}",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(document_id: str = "doc-1", chunk_id: str = "chunk-1") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=0,
        text="RAG store notes with an embedding metadata reference.",
        citation_anchor_id="anchor-1",
        token_estimate=9,
        byte_start=0,
        byte_end=57,
        embedding_model="local-bge-small-en-v1.5",
        embedding_vector_id="vec-1",
    )


def _anchor(document_id: str = "doc-1", chunk_id: str = "chunk-1") -> CitationAnchor:
    return CitationAnchor(
        id="anchor-1",
        document_id=document_id,
        chunk_id=chunk_id,
        label="p. 1",
        source_path_or_url="/profiles/work/brain/assets/doc-1.md",
        display_range="bytes 0-57",
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
        self.documents: dict[tuple[str, str], dict[str, Any]] = {}
        self.chunks: dict[tuple[str, str], dict[str, Any]] = {}
        self.anchors: dict[tuple[str, str], dict[str, Any]] = {}

    def __enter__(self) -> "_FakePostgresConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def cursor(self) -> "_FakePostgresCursor":
        return _FakePostgresCursor(self)


class _FakePostgresCursor:
    def __init__(self, connection: _FakePostgresConnection) -> None:
        self.connection = connection
        self.rows: list[dict[str, Any]] = []

    def __enter__(self) -> "_FakePostgresCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> "_FakePostgresCursor":
        bound_params = tuple(params or ())
        self.connection.executed.append((sql, bound_params))
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert into documents"):
            self._upsert_document(bound_params)
        elif normalized.startswith("insert into document_chunks"):
            self._upsert_chunk(bound_params)
        elif normalized.startswith("insert into citation_anchors"):
            self._upsert_anchor(bound_params)
        elif "from documents" in normalized and "where profile_id = %s and id = %s" in normalized:
            self.rows = [
                self.connection.documents[(bound_params[0], bound_params[1])]
            ] if (bound_params[0], bound_params[1]) in self.connection.documents else []
        elif "from documents" in normalized and "where profile_id = %s" in normalized:
            self.rows = [
                row
                for (profile_id, _), row in self.connection.documents.items()
                if profile_id == bound_params[0]
            ]
        elif "from document_chunks" in normalized:
            self.rows = [
                row
                for row in self.connection.chunks.values()
                if row["profile_id"] == bound_params[0]
                and row["document_id"] == bound_params[1]
            ]
        elif "from citation_anchors" in normalized:
            self.rows = [
                row
                for row in self.connection.anchors.values()
                if row["profile_id"] == bound_params[0]
                and row["document_id"] == bound_params[1]
            ]
        else:
            self.rows = []
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def _upsert_document(self, params: tuple[Any, ...]) -> None:
        self.connection.documents[(params[0], params[1])] = {
            "profile_id": params[0],
            "id": params[1],
            "source_type": params[2],
            "raw_asset_path": params[3],
            "parsed_representation_path": params[4],
            "title": params[5],
            "metadata_json": params[6],
            "content_hash": params[7],
            "parser": params[8],
            "created_at": params[9],
            "updated_at": params[10],
        }

    def _upsert_chunk(self, params: tuple[Any, ...]) -> None:
        self.connection.chunks[(params[0], params[1])] = {
            "profile_id": params[0],
            "id": params[1],
            "document_id": params[2],
            "chunk_index": params[3],
            "text": params[4],
            "citation_anchor_id": params[5],
            "token_estimate": params[6],
            "byte_start": params[7],
            "byte_end": params[8],
            "embedding_model": params[9],
            "embedding_vector_id": params[10],
        }

    def _upsert_anchor(self, params: tuple[Any, ...]) -> None:
        self.connection.anchors[(params[0], params[1])] = {
            "profile_id": params[0],
            "id": params[1],
            "document_id": params[2],
            "chunk_id": params[3],
            "label": params[4],
            "source_path_or_url": params[5],
            "display_range": params[6],
        }


def _first_statement(
    executed: list[tuple[str, tuple[Any, ...]]],
    token: str,
) -> tuple[str, tuple[Any, ...]]:
    for sql, params in executed:
        if token in sql:
            return sql, params
    raise AssertionError(f"missing SQL statement containing {token!r}")


def test_sqlite_store_persists_document_chunks_citations_and_embedding_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="air-offline",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    document = _document(profile.name)
    chunk = _chunk()
    anchor = _anchor()

    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)
    store.upsert_citation_anchor(profile, anchor)

    assert store.get_document(profile, document.id) == document
    assert store.list_chunks(profile, document.id) == [chunk]
    assert store.list_citation_anchors(profile, document.id) == [anchor]
    assert store.list_chunks(profile, document.id)[0].embedding_model == (
        "local-bge-small-en-v1.5"
    )
    assert store.list_chunks(profile, document.id)[0].embedding_vector_id == "vec-1"


def test_postgres_store_initializes_schema_and_persists_document_chunks_citations(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    connection_factory = _FakePostgresConnectionFactory()
    store = ProfileRagStore.postgres(connection_factory)
    document = _document(profile.name)
    chunk = _chunk()
    anchor = _anchor()

    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)
    store.upsert_citation_anchor(profile, anchor)

    assert store.get_document(profile, document.id) == document
    assert store.list_chunks(profile, document.id) == [chunk]
    assert store.list_citation_anchors(profile, document.id) == [anchor]

    assert any(
        "CREATE EXTENSION IF NOT EXISTS vector" in sql
        for sql, _ in connection_factory.executed
    )
    document_sql, document_params = _first_statement(
        connection_factory.executed,
        "INSERT INTO documents",
    )
    chunk_sql, chunk_params = _first_statement(
        connection_factory.executed,
        "INSERT INTO document_chunks",
    )
    anchor_sql, anchor_params = _first_statement(
        connection_factory.executed,
        "INSERT INTO citation_anchors",
    )
    for sql in (document_sql, chunk_sql, anchor_sql):
        assert "%s" in sql
        assert "?" not in sql
        assert "ON CONFLICT(profile_id, id) DO UPDATE SET" in sql
    assert document_params[:2] == (profile.name, document.id)
    assert document_params[6] == json.dumps(
        document.metadata,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert chunk_params[:3] == (profile.name, chunk.id, document.id)
    assert anchor_params[:4] == (profile.name, anchor.id, document.id, chunk.id)


def test_postgres_store_keeps_profile_isolation_and_document_ledger(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
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
    connection_factory = _FakePostgresConnectionFactory()
    store = ProfileRagStore.postgres(connection_factory)
    work_document = _document(work.name, "shared-id")
    personal_document = _document(personal.name, "shared-id")

    store.upsert_document(work, work_document)
    store.upsert_document(personal, personal_document)

    assert store.get_document(work, "shared-id") == work_document
    assert store.get_document(personal, "shared-id") == personal_document
    assert store.list_documents(work) == [work_document]
    assert store.list_documents(personal) == [personal_document]

    work_ledger = Path(work.root) / "brain" / "ledgers" / "documents.jsonl"
    personal_ledger = Path(personal.root) / "brain" / "ledgers" / "documents.jsonl"
    work_rows = [
        json.loads(line)
        for line in work_ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    personal_rows = [
        json.loads(line)
        for line in personal_ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["payload"]["document"]["profile_id"] for row in work_rows] == [
        work.name
    ]
    assert [row["payload"]["document"]["profile_id"] for row in personal_rows] == [
        personal.name
    ]


def test_store_rejects_document_with_mismatched_profile_id(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")

    with pytest.raises(RagStoreError, match="document profile_id must match"):
        store.upsert_document(profile, _document("personal"))


def test_store_does_not_read_documents_across_profiles(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
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
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    work_document = _document(work.name, "shared-id")
    personal_document = _document(personal.name, "shared-id")

    store.upsert_document(work, work_document)
    store.upsert_document(personal, personal_document)

    assert store.get_document(work, "shared-id") == work_document
    assert store.get_document(personal, "shared-id") == personal_document
    assert store.list_documents(work) == [work_document]
    assert store.list_documents(personal) == [personal_document]


def test_document_mutations_are_appended_to_documents_jsonl_and_replay_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    original = _document(profile.name)
    updated = Document(
        **{
            **original.to_dict(),
            "title": "updated title",
            "metadata": {"source_name": "doc-1.md", "page_count": 4},
            "updated_at": "2026-06-04T12:05:00+00:00",
        }
    )

    store.upsert_document(profile, original)
    store.upsert_document(profile, updated)

    ledger_path = Path(profile.root) / "brain" / "ledgers" / "documents.jsonl"
    rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["record_id"] for row in rows] == [original.id, updated.id]
    assert rows[-1]["payload"]["event"] == "document.upserted"
    assert rows[-1]["payload"]["document"]["profile_id"] == profile.name

    replayed = replay_document_metadata(profile)

    assert replayed == {updated.id: updated}


def test_rag_schema_supports_sqlite_logical_storage_and_postgres_pgvector() -> None:
    assert "CREATE TABLE IF NOT EXISTS documents" in SQLITE_RAG_SCHEMA_SQL
    assert "metadata_json TEXT NOT NULL" in SQLITE_RAG_SCHEMA_SQL
    assert "embedding_model TEXT" in SQLITE_RAG_SCHEMA_SQL
    assert "embedding_vector_id TEXT" in SQLITE_RAG_SCHEMA_SQL
    assert "vector(" not in SQLITE_RAG_SCHEMA_SQL
    assert "JSONB" not in SQLITE_RAG_SCHEMA_SQL

    assert "CREATE EXTENSION IF NOT EXISTS vector" in POSTGRES_RAG_SCHEMA_SQL
    assert "metadata JSONB NOT NULL" in POSTGRES_RAG_SCHEMA_SQL
    assert "embedding vector(384)" in POSTGRES_RAG_SCHEMA_SQL
    assert "USING hnsw (embedding vector_cosine_ops)" in POSTGRES_RAG_SCHEMA_SQL
    assert "PRIMARY KEY (profile_id, id)" in POSTGRES_RAG_SCHEMA_SQL
