from pathlib import Path

from zsper.brain.compose import render_brain_profile
from zsper.brain.db.schema import SCHEMA_SQL, render_schema_sql, schema_tables
from zsper.profiles import initialize_profile


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
    "settings",
}


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
        assert "profile_name TEXT NOT NULL" in table_sql
        assert "FOREIGN KEY (profile_id, profile_name)" in table_sql


def test_schema_sql_has_full_text_and_vector_indexes() -> None:
    sql = render_schema_sql()

    for table in (
        "documents",
        "document_chunks",
        "notes",
        "tasks",
        "memory_events",
        "research_records",
        "chat_messages",
        "agent_run_events",
    ):
        assert f"idx_{table}_search_vector" in sql

    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "idx_document_chunks_embedding" in sql
    assert "idx_memory_events_embedding" in sql
    assert "idx_research_records_embedding" in sql


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
