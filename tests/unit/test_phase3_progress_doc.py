from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKING_DOC = REPO_ROOT / "docs" / "superpowers" / "plans" / "phase-3-progress.md"


def test_phase3_progress_tracking_doc_exists() -> None:
    text = TRACKING_DOC.read_text(encoding="utf-8")

    assert "Phase 3 Progress" in text
    assert "docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md" in text
    for task_id in (
        "BRAIN-001",
        "BRAIN-002",
        "BRAIN-003",
        "BRAIN-004",
        "BRAIN-005",
        "BRAIN-006",
        "BRAIN-007",
        "BRAIN-008",
        "BRAIN-009",
        "GATE-001",
    ):
        assert task_id in text
