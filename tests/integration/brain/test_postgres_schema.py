import re

import pytest

from zsper.brain.db.schema import render_schema_sql, schema_tables


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


@pytest.mark.integration
def test_initial_migration_sql_shape_is_self_contained() -> None:
    sql = render_schema_sql()

    assert "\\i" not in sql
    assert "{{" not in sql
    assert "}}" not in sql
    assert sql.count("CREATE TABLE IF NOT EXISTS") == len(REQUIRED_TABLES)
    assert REQUIRED_TABLES == set(schema_tables(sql))
    assert sql.rstrip().endswith("-- zsper brain initial schema")


@pytest.mark.integration
def test_initial_migration_has_profile_scoped_foreign_keys() -> None:
    sql = render_schema_sql()

    for table in REQUIRED_TABLES - {"profile_metadata"}:
        pattern = (
            rf"CREATE TABLE IF NOT EXISTS {table}\s*\("
            rf".*?FOREIGN KEY \(profile_id, profile_name\) "
            rf"REFERENCES profile_metadata \(profile_id, profile_name\)"
        )
        assert re.search(pattern, sql, re.DOTALL), table


@pytest.mark.integration
def test_initial_migration_orders_parent_tables_before_dependents() -> None:
    sql = render_schema_sql()

    assert sql.index("CREATE TABLE IF NOT EXISTS profile_metadata") < sql.index(
        "CREATE TABLE IF NOT EXISTS documents"
    )
    assert sql.index("CREATE TABLE IF NOT EXISTS documents") < sql.index(
        "CREATE TABLE IF NOT EXISTS document_chunks"
    )
    assert sql.index("CREATE TABLE IF NOT EXISTS chat_sessions") < sql.index(
        "CREATE TABLE IF NOT EXISTS chat_messages"
    )
    assert sql.index("CREATE TABLE IF NOT EXISTS agent_runs") < sql.index(
        "CREATE TABLE IF NOT EXISTS agent_run_events"
    )
