import json
from pathlib import Path

from zsper.brain.ledgers import LedgerKind, append_ledger_record, read_ledger_records
from zsper.profiles import initialize_profile


def test_append_ledger_record_writes_valid_profile_scoped_jsonl(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )

    first = append_ledger_record(
        profile,
        LedgerKind.DOCUMENTS,
        record_id="doc-1",
        payload={"event": "document.created", "title": "First"},
    )
    second = append_ledger_record(
        profile,
        LedgerKind.DOCUMENTS,
        record_id="doc-2",
        payload={"event": "document.created", "title": "Second"},
    )

    assert first == second == Path(profile.root) / "brain" / "ledgers" / "documents.jsonl"
    rows = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    assert [row["record_id"] for row in rows] == ["doc-1", "doc-2"]
    assert rows[0]["profile_id"] == profile.name
    assert rows[0]["profile_name"] == profile.name
    assert rows[0]["payload"]["title"] == "First"


def test_ledgers_redact_secrets_before_writing(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )

    path = append_ledger_record(
        profile,
        LedgerKind.TASKS,
        record_id="task-1",
        payload={
            "event": "task.created",
            "api_key": "real-key",
            "nested": {"authorization": "Bearer secret", "safe": "kept"},
        },
    )

    text = path.read_text(encoding="utf-8")
    assert "real-key" not in text
    assert "Bearer secret" not in text
    row = json.loads(text)
    assert row["payload"]["api_key"] == "[REDACTED]"
    assert row["payload"]["nested"]["authorization"] == "[REDACTED]"
    assert row["payload"]["nested"]["safe"] == "kept"


def test_agent_run_ledgers_and_replay_do_not_require_services(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )

    runs_path = append_ledger_record(
        profile,
        LedgerKind.AGENT_RUNS,
        record_id="run-1",
        payload={"event": "agent_run.created"},
    )
    events_path = append_ledger_record(
        profile,
        LedgerKind.AGENT_RUN_EVENTS,
        record_id="event-1",
        payload={"event": "agent_run.output", "chunk": "started"},
        run_id="run-1",
    )

    assert runs_path == Path(profile.root) / "agent-runs" / "runs.jsonl"
    assert events_path == Path(profile.root) / "agent-runs" / "events" / "run-1.jsonl"
    assert read_ledger_records(profile, LedgerKind.AGENT_RUNS)[0]["record_id"] == "run-1"
    assert read_ledger_records(
        profile,
        LedgerKind.AGENT_RUN_EVENTS,
        run_id="run-1",
    )[0]["payload"]["chunk"] == "started"
