"""Append-only profile ledgers for Brain records and agent runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from zsper.profiles import Profile
from zsper.security.redaction import redact_secrets


class LedgerError(ValueError):
    """Raised when a ledger operation is invalid."""


class LedgerKind(str, Enum):
    DOCUMENTS = "documents"
    MEMORY_EVENTS = "memory-events"
    TASKS = "tasks"
    AGENT_RUNS = "agent-runs"
    AGENT_RUN_EVENTS = "agent-run-events"


@dataclass(frozen=True)
class LedgerRecord:
    profile_id: str
    profile_name: str
    ledger: str
    record_id: str
    payload: dict[str, Any]
    written_at: str
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "ledger": self.ledger,
            "payload": self.payload,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "record_id": self.record_id,
            "written_at": self.written_at,
        }
        if self.run_id is not None:
            row["run_id"] = self.run_id
        return row


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ledger_path(profile: Profile, kind: LedgerKind, *, run_id: str | None = None) -> Path:
    root = Path(profile.root)
    if kind == LedgerKind.DOCUMENTS:
        return root / "brain" / "ledgers" / "documents.jsonl"
    if kind == LedgerKind.MEMORY_EVENTS:
        return root / "brain" / "ledgers" / "memory-events.jsonl"
    if kind == LedgerKind.TASKS:
        return root / "brain" / "ledgers" / "tasks.jsonl"
    if kind == LedgerKind.AGENT_RUNS:
        return root / "agent-runs" / "runs.jsonl"
    if kind == LedgerKind.AGENT_RUN_EVENTS:
        if not run_id:
            raise LedgerError("run_id is required for agent run event ledgers")
        return root / "agent-runs" / "events" / f"{run_id}.jsonl"
    raise LedgerError(f"unsupported ledger kind: {kind}")


def append_ledger_record(
    profile: Profile,
    kind: LedgerKind,
    *,
    record_id: str,
    payload: dict[str, Any],
    run_id: str | None = None,
) -> Path:
    path = ledger_path(profile, kind, run_id=run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = LedgerRecord(
        profile_id=profile.name,
        profile_name=profile.name,
        ledger=kind.value,
        record_id=record_id,
        payload=redact_secrets(payload),
        run_id=run_id,
        written_at=_utc_now(),
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_secrets(record.to_dict()), sort_keys=True) + "\n")
    return path


def read_ledger_records(
    profile: Profile,
    kind: LedgerKind,
    *,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    path = ledger_path(profile, kind, run_id=run_id)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records
