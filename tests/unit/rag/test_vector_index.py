from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag.models import Document, DocumentChunk


def _vector_api() -> tuple[Any, Any, Any]:
    try:
        from zsper.rag.indexes import (
            ProfileVectorIndex,
            VectorIndexError,
            VectorSearchResult,
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"Vector index API is missing: {exc}")
    return ProfileVectorIndex, VectorIndexError, VectorSearchResult


def _document(profile: Profile, document_id: str = "doc-1") -> Document:
    source_path = Path(profile.root) / "brain" / "documents" / f"{document_id}.md"
    return Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(source_path),
        parsed_representation_path=str(source_path.with_suffix(".txt")),
        title=f"{profile.name} vector fixture",
        metadata={"source_name": source_path.name},
        content_hash=f"sha256:{profile.name}-{document_id}",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(
    profile: Profile,
    document_id: str,
    chunk_id: str,
    text: str,
    *,
    chunk_index: int = 0,
    vector_id: str | None = None,
    embedding_model: str | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        citation_anchor_id=f"anchor-{chunk_id}",
        token_estimate=max(1, len(text.split())),
        byte_start=chunk_index * 100,
        byte_end=chunk_index * 100 + len(text.encode("utf-8")),
        embedding_model=embedding_model if embedding_model is not None else profile.embedding_profile,
        embedding_vector_id=vector_id if vector_id is not None else f"vec-{profile.name}-{chunk_id}",
    )


def test_sqlite_vector_search_returns_semantic_fixture_chunk(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileVectorIndex, _, VectorSearchResult = _vector_api()
    profile = initialize_profile(
        mode="air-offline",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
    )
    document = _document(profile)
    irrelevant = _chunk(
        profile,
        document.id,
        "chunk-scheduler",
        "The scheduler records tmux run state and task status.",
        chunk_index=0,
    )
    relevant = _chunk(
        profile,
        document.id,
        "chunk-citations",
        "Citation anchors preserve source ranges for document answers.",
        chunk_index=1,
    )
    index = ProfileVectorIndex.sqlite(tmp_path / "vectors.sqlite")

    index.index_chunks(
        profile,
        document,
        [irrelevant, relevant],
        vectors_by_chunk_id={
            irrelevant.id: (0.0, 1.0, 0.0),
            relevant.id: (1.0, 0.0, 0.0),
        },
    )
    results = index.search(
        profile,
        query_vector=(0.92, 0.08, 0.0),
        embedding_model=profile.embedding_profile,
        limit=2,
    )

    assert results
    assert isinstance(results[0], VectorSearchResult)
    assert [result.chunk_id for result in results] == [relevant.id, irrelevant.id]
    assert results[0].profile_id == profile.name
    assert results[0].document_id == document.id
    assert results[0].embedding_model == profile.embedding_profile
    assert results[0].embedding_vector_id == relevant.embedding_vector_id
    assert results[0].score > results[1].score


def test_sqlite_vector_search_is_profile_scoped(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileVectorIndex, _, _ = _vector_api()
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
        work,
        work_document.id,
        "shared-chunk",
        "Work-only semantic fixture.",
        vector_id="vec-work-shared",
    )
    personal_chunk = _chunk(
        personal,
        personal_document.id,
        "shared-chunk",
        "Personal-only semantic fixture.",
        vector_id="vec-personal-shared",
    )
    index = ProfileVectorIndex.sqlite(tmp_path / "vectors.sqlite")

    index.index_chunks(
        work,
        work_document,
        [work_chunk],
        vectors_by_chunk_id={work_chunk.id: (1.0, 0.0, 0.0)},
    )
    index.index_chunks(
        personal,
        personal_document,
        [personal_chunk],
        vectors_by_chunk_id={personal_chunk.id: (0.0, 1.0, 0.0)},
    )

    work_results = index.search(
        work,
        query_vector=(1.0, 0.0, 0.0),
        embedding_model=work.embedding_profile,
    )
    personal_results = index.search(
        personal,
        query_vector=(0.0, 1.0, 0.0),
        embedding_model=personal.embedding_profile,
    )

    assert [(result.profile_id, result.chunk_id) for result in work_results] == [
        (work.name, work_chunk.id)
    ]
    assert [(result.profile_id, result.chunk_id) for result in personal_results] == [
        (personal.name, personal_chunk.id)
    ]


def test_vector_index_requires_embedding_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileVectorIndex, VectorIndexError, _ = _vector_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    document = _document(profile)
    chunk = _chunk(
        profile,
        document.id,
        "chunk-without-vector-id",
        "Vector rows need the chunk embedding identity.",
        vector_id="temporary",
    )
    chunk_without_metadata = DocumentChunk(
        **{
            **chunk.to_dict(),
            "embedding_model": None,
            "embedding_vector_id": None,
        }
    )
    index = ProfileVectorIndex.sqlite(tmp_path / "vectors.sqlite")

    with pytest.raises(VectorIndexError, match="embedding metadata"):
        index.index_chunks(
            profile,
            document,
            [chunk_without_metadata],
            vectors_by_chunk_id={chunk_without_metadata.id: (1.0, 0.0, 0.0)},
        )


def test_vector_index_rejects_mismatched_document_profile(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    ProfileVectorIndex, VectorIndexError, _ = _vector_api()
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
    personal_document = _document(personal)
    chunk = _chunk(personal, personal_document.id, "chunk-personal", "Personal row.")
    index = ProfileVectorIndex.sqlite(tmp_path / "vectors.sqlite")

    with pytest.raises(VectorIndexError, match="document profile_id must match"):
        index.index_chunks(
            work,
            personal_document,
            [chunk],
            vectors_by_chunk_id={chunk.id: (1.0, 0.0, 0.0)},
        )
