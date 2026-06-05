from pathlib import Path

from zsper.brain.compose import render_brain_profile
from zsper.brain.db.schema import SCHEMA_SQL, render_schema_sql, schema_tables
from zsper.profiles import initialize_profile
from zsper.rag.indexes.vector import POSTGRES_VECTOR_SCHEMA_SQL
from zsper.rag.store import POSTGRES_RAG_SCHEMA_SQL


REQUIRED_TABLES = {
    "profile_metadata",
    "documents",
    "document_chunks",
    "citation_anchors",
    "notes",
    "tasks",
    "memory_events",
    "research_records",
    "chat_sessions",
    "chat_messages",
    "agent_runs",
    "agent_run_events",
    "rag_chunk_vectors",
    "settings",
}

RAG_TABLES = {"documents", "document_chunks", "citation_anchors"}
PROFILE_METADATA_TABLES = REQUIRED_TABLES - RAG_TABLES - {"profile_metadata", "rag_chunk_vectors"}


def _table_sql(sql: str, table: str) -> str:
    start = sql.index(f"CREATE TABLE IF NOT EXISTS {table}")
    end = sql.index(");", start)
    return sql[start:end]


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_schema_profile_id_type_matches_rendered_env_contract(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    rendered_profile_ids: list[str] = []
    for mode in ("work", "personal"):
        profile = initialize_profile(
            mode=mode,
            root=tmp_path / mode,
            registry_path=isolated_registry_path,
        )
        rendered = render_brain_profile(profile, repo_root=tmp_path / "repo")
        rendered_profile_ids.append(_env_values(rendered.env_path)["ZSPER_PROFILE_ID"])

    assert rendered_profile_ids == ["work", "personal"]

    sql = render_schema_sql()
    assert "profile_id UUID" not in sql
    for table in REQUIRED_TABLES:
        assert "profile_id TEXT NOT NULL" in _table_sql(sql, table)


def test_schema_sql_contains_required_pgvector_tables_and_profile_scope() -> None:
    sql = render_schema_sql()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert REQUIRED_TABLES <= set(schema_tables(sql))
    for table in REQUIRED_TABLES - {"profile_metadata"}:
        table_sql = _table_sql(sql, table)
        assert "profile_id TEXT NOT NULL" in table_sql

    for table in PROFILE_METADATA_TABLES:
        table_sql = _table_sql(sql, table)
        assert "profile_name TEXT NOT NULL" in table_sql
        assert "FOREIGN KEY (profile_id, profile_name)" in table_sql


def test_schema_sql_uses_rag_store_document_contract() -> None:
    sql = render_schema_sql()
    documents = _table_sql(sql, "documents")
    chunks = _table_sql(sql, "document_chunks")
    anchors = _table_sql(sql, "citation_anchors")

    assert POSTGRES_RAG_SCHEMA_SQL.strip() in sql

    for required in (
        "id TEXT NOT NULL",
        "raw_asset_path TEXT NOT NULL",
        "parsed_representation_path TEXT NOT NULL",
        "content_hash TEXT NOT NULL",
        "parser TEXT NOT NULL",
        "PRIMARY KEY (profile_id, id)",
    ):
        assert required in documents
    for old_shape in (
        "document_id UUID",
        "source_uri TEXT",
        "\n  asset_path TEXT",
        "\n  parsed_path TEXT",
    ):
        assert old_shape not in documents

    for required in (
        "id TEXT NOT NULL",
        "document_id TEXT NOT NULL",
        "text TEXT NOT NULL",
        "citation_anchor_id TEXT NOT NULL",
        "token_estimate INTEGER NOT NULL",
        "embedding_model TEXT",
        "embedding_vector_id TEXT",
        "FOREIGN KEY (profile_id, document_id) REFERENCES documents (profile_id, id)",
    ):
        assert required in chunks
    for old_shape in ("chunk_id UUID", "content TEXT NOT NULL", "token_count INTEGER"):
        assert old_shape not in chunks

    for required in (
        "id TEXT NOT NULL",
        "document_id TEXT NOT NULL",
        "chunk_id TEXT NOT NULL",
        "source_path_or_url TEXT NOT NULL",
        "display_range TEXT",
        "FOREIGN KEY (profile_id, document_id) REFERENCES documents (profile_id, id)",
        "FOREIGN KEY (profile_id, chunk_id) REFERENCES document_chunks (profile_id, id)",
    ):
        assert required in anchors
    for old_shape in ("anchor_id UUID", "locator TEXT", "quote TEXT", "chunk_id UUID"):
        assert old_shape not in anchors


def test_schema_sql_includes_vector_index_contract() -> None:
    sql = render_schema_sql()
    vectors = _table_sql(sql, "rag_chunk_vectors")

    assert POSTGRES_VECTOR_SCHEMA_SQL.strip() in sql
    for required in (
        "profile_id TEXT NOT NULL",
        "document_id TEXT NOT NULL",
        "chunk_id TEXT NOT NULL",
        "embedding_model TEXT NOT NULL",
        "embedding_vector_id TEXT NOT NULL",
        "embedding vector(384) NOT NULL",
        "PRIMARY KEY (profile_id, document_id, chunk_id, embedding_model)",
        "UNIQUE (profile_id, embedding_vector_id)",
    ):
        assert required in vectors
    assert "idx_rag_chunk_vectors_embedding" in sql


def test_schema_sql_has_full_text_and_vector_indexes() -> None:
    sql = render_schema_sql()

    for table in (
        "notes",
        "tasks",
        "memory_events",
        "research_records",
        "chat_messages",
        "agent_run_events",
    ):
        assert f"idx_{table}_search_vector" in sql

    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "idx_memory_events_embedding" in sql
    assert "idx_research_records_embedding" in sql
    assert "idx_rag_document_chunks_embedding" in sql
    assert "idx_rag_chunk_vectors_embedding" in sql


def test_brain_render_emits_schema_sql(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )

    rendered = render_brain_profile(profile, repo_root=tmp_path / "repo")

    assert rendered.schema_path == Path(profile.root) / "brain" / "schema.sql"
    assert rendered.schema_path.read_text(encoding="utf-8") == SCHEMA_SQL


def test_checked_in_initial_migration_matches_rendered_schema() -> None:
    migration_path = (
        Path(__file__).parents[3] / "services" / "brain-api" / "migrations" / "0001_initial.sql"
    )

    assert migration_path.read_text(encoding="utf-8") == render_schema_sql()
