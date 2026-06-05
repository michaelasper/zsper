from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKING_DOC = REPO_ROOT / "docs" / "superpowers" / "plans" / "phase-4-progress.md"


def test_phase4_progress_doc_tracks_all_rag_tasks() -> None:
    text = TRACKING_DOC.read_text(encoding="utf-8")

    for task_id in (
        "RAG-001",
        "RAG-002",
        "RAG-003",
        "RAG-004",
        "RAG-005",
        "RAG-006",
        "RAG-007",
        "RAG-008",
        "RAG-009",
        "RAG-010",
        "RAG-011",
        "RAG-012",
        "RAG-013",
        "RAG-014",
        "RAG-015",
        "RAG-016",
        "GATE-002",
    ):
        assert task_id in text

    assert "parallel" in text.lower()
    assert "citation objects" in text
