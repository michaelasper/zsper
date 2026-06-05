from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKING_DOC = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "air-offline-out-of-order-progress.md"
)


def test_air_offline_out_of_order_tracking_doc_exists() -> None:
    text = TRACKING_DOC.read_text(encoding="utf-8")

    assert "Out-Of-Order Portable Profile Work" in text
    assert "docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md" in text
    assert "Gemma 4 12B" in text
    assert "profile init/show/list/doctor" in text
    assert "local-file ingest/search" in text
    assert "deferred" in text.lower()
    assert "Phase 4 RAG now covers Docling" in text
    assert "Docling parsing for PDFs, Office files, and complex HTML." not in text
    assert "Chunk records, citation anchors, BM25 indexes" not in text
    assert "`brain answer` with citation objects." not in text
