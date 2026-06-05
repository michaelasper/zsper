from pathlib import Path
from typing import Any

import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag.models import Document, DocumentChunk


def _bm25_api() -> tuple[Any, Any]:
    try:
        from zsper.rag.indexes import Bm25SearchResult, ProfileBm25Index
    except ModuleNotFoundError as exc:
        pytest.fail(f"BM25 API is missing: {exc}")
    return ProfileBm25Index, Bm25SearchResult


def _document(
    profile: Profile,
    *,
    document_id: str = "doc-1",
    metadata: dict[str, Any] | None = None,
) -> Document:
    source_path = Path(profile.root) / "brain" / "documents" / f"{document_id}.md"
    return Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(source_path),
        parsed_representation_path=str(source_path.with_suffix(".txt")),
        title=f"{profile.name} BM25 fixture",
        metadata={
            "source_name": source_path.name,
            "source_path": str(source_path),
            **(metadata or {}),
        },
        content_hash=f"sha256:{profile.name}-{document_id}",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(
    document_id: str,
    chunk_id: str,
    text: str,
    *,
    chunk_index: int = 0,
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        citation_anchor_id=f"anchor-{chunk_id}",
        token_estimate=max(1, len(text.split())),
        byte_start=0,
        byte_end=len(text.encode("utf-8")),
        embedding_model=None,
        embedding_vector_id=None,
    )


def test_search_returns_exact_error_string_from_chunk_text(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileBm25Index, Bm25SearchResult = _bm25_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    document = _document(profile)
    semantic_only = _chunk(
        document.id,
        "chunk-semantic",
        "Troubleshooting notes for local index worker startup and recovery.",
        chunk_index=0,
    )
    exact = _chunk(
        document.id,
        "chunk-exact",
        "Worker failed with ModuleNotFoundError: No module named "
        "'zsper.rag.indexes.bm25' while loading the local RAG index.",
        chunk_index=1,
    )
    index = ProfileBm25Index.sqlite(tmp_path / "bm25.sqlite")

    index.index_chunks(profile, document, [semantic_only, exact])
    results = index.search(
        profile,
        "ModuleNotFoundError: No module named zsper.rag.indexes.bm25",
        limit=3,
    )

    assert results
    assert isinstance(results[0], Bm25SearchResult)
    assert results[0].profile_id == profile.name
    assert results[0].document_id == document.id
    assert results[0].chunk_id == exact.id
    assert results[0].score > 0
    assert "ModuleNotFoundError" in results[0].text_preview


def test_search_indexes_document_and_chunk_metadata_for_file_paths(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileBm25Index, _ = _bm25_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    exact_path = "/Users/michaelasper/source/zsper/src/zsper/rag/indexes/bm25.py"
    document = _document(
        profile,
        metadata={
            "command": "pytest tests/unit/rag/test_bm25.py -v",
        },
    )
    metadata_match = _chunk(
        document.id,
        "chunk-path",
        "This chunk describes the local BM25 index module without spelling out its path.",
    )
    other = _chunk(
        document.id,
        "chunk-other",
        "This chunk mentions src/zsper/rag and Python modules in general.",
        chunk_index=1,
    )
    index = ProfileBm25Index.sqlite(tmp_path / "bm25.sqlite")

    index.index_chunks(
        profile,
        document,
        [metadata_match, other],
        metadata_by_chunk_id={
            metadata_match.id: {"citation": "RAG-010", "source_path": exact_path}
        },
    )
    results = index.search(profile, exact_path, limit=2)

    assert [result.chunk_id for result in results][:1] == [metadata_match.id]
    assert results[0].document_id == document.id


def test_work_and_personal_profiles_cannot_read_each_others_bm25_rows(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileBm25Index, _ = _bm25_api()
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
    work_document = _document(work, document_id="shared-doc")
    personal_document = _document(personal, document_id="shared-doc")
    work_chunk = _chunk(
        work_document.id,
        "shared-chunk",
        "zworkneedle-only-BM25-token appears in the work profile row.",
    )
    personal_chunk = _chunk(
        personal_document.id,
        "shared-chunk",
        "zpersonalneedle-only-BM25-token appears in the personal profile row.",
    )
    index = ProfileBm25Index.sqlite(tmp_path / "bm25.sqlite")

    index.index_chunks(work, work_document, [work_chunk])
    index.index_chunks(personal, personal_document, [personal_chunk])

    assert [
        result.chunk_id
        for result in index.search(work, "zworkneedle-only-BM25-token")
    ] == [work_chunk.id]
    assert index.search(work, "zpersonalneedle-only-BM25-token") == []
    assert [
        result.chunk_id
        for result in index.search(personal, "zpersonalneedle-only-BM25-token")
    ] == [personal_chunk.id]
    assert index.search(personal, "zworkneedle-only-BM25-token") == []
