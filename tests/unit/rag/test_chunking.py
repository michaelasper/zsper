import json
from pathlib import Path
from typing import Any

import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag import Document, ProfileRagStore


def _chunking_api() -> tuple[Any, Any]:
    try:
        from zsper.rag.chunking import ChunkingResult, chunk_document
    except ModuleNotFoundError as exc:
        pytest.fail(f"chunking API is missing: {exc}")
    return chunk_document, ChunkingResult


def _document(
    profile: Profile,
    parsed_path: Path,
    *,
    document_id: str = "doc-1",
    parser: str = "text",
    content_hash: str = "sha256:fixture",
    version: int = 1,
) -> Document:
    return Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(parsed_path.with_suffix(".raw")),
        parsed_representation_path=str(parsed_path),
        title="Chunk Fixture",
        metadata={
            "original_path": str(parsed_path.with_suffix(".source")),
            "original_url": None,
            "source_filename": parsed_path.name,
            "version": version,
        },
        content_hash=content_hash,
        parser=parser,
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def test_text_chunking_persists_stable_ids_offsets_and_token_estimates(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    chunk_document, chunking_result_type = _chunking_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    parsed_path = tmp_path / "parsed" / "notes.txt"
    parsed_path.parent.mkdir()
    text = (
        "# Incident Notes\n\n"
        "The local worker restarts from the profile runtime directory.\n\n"
        "Operators verify the exact command, file path, and final status before "
        "closing the task.\n"
    )
    parsed_path.write_text(text, encoding="utf-8")
    document = _document(profile, parsed_path)
    store.upsert_document(profile, document)

    first = chunk_document(
        profile,
        store,
        document,
        max_chunk_chars=72,
        overlap_chars=8,
    )
    second = chunk_document(
        profile,
        store,
        document,
        max_chunk_chars=72,
        overlap_chars=8,
    )

    assert isinstance(first, chunking_result_type)
    assert len(first.chunks) >= 2
    assert [chunk.id for chunk in first.chunks] == [
        chunk.id for chunk in second.chunks
    ]
    assert store.list_chunks(profile, document.id) == list(second.chunks)

    text_bytes = text.encode("utf-8")
    for index, chunk in enumerate(first.chunks):
        assert chunk.chunk_index == index
        assert chunk.id.startswith("chunk-")
        assert chunk.citation_anchor_id.startswith("anchor-pending-")
        assert chunk.token_estimate > 0
        assert chunk.byte_start is not None
        assert chunk.byte_end is not None
        assert text_bytes[chunk.byte_start : chunk.byte_end].decode("utf-8") == chunk.text
        assert first.location_by_chunk_id[chunk.id].byte_start == chunk.byte_start
        assert first.location_by_chunk_id[chunk.id].byte_end == chunk.byte_end


def test_docling_chunking_returns_segment_location_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    chunk_document, _ = _chunking_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    parsed_path = tmp_path / "parsed" / "runbook.json"
    parsed_path.parent.mkdir()
    text = "# Incident Runbook\n\nRestart the local worker from the profile runtime."
    parsed_path.write_text(
        json.dumps(
            {
                "schema": "zsper.rag.docling_parsed.v1",
                "document_id": "doc-pdf",
                "parser": "docling",
                "text": text,
                "segments": [
                    {
                        "index": 0,
                        "text": "# Incident Runbook",
                        "page": 1,
                        "heading": "Incident Runbook",
                        "section": "Overview",
                        "metadata": {"kind": "heading"},
                    },
                    {
                        "index": 1,
                        "text": "Restart the local worker from the profile runtime.",
                        "page": 2,
                        "heading": "Incident Runbook",
                        "section": "Recovery",
                        "metadata": {"kind": "paragraph", "bbox": [1, 2, 3, 4]},
                    },
                ],
                "metadata": {"document_title": "Runbook"},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    document = _document(
        profile,
        parsed_path,
        document_id="doc-pdf",
        parser="docling",
        content_hash="sha256:pdf-fixture",
    )
    store.upsert_document(profile, document)

    result = chunk_document(
        profile,
        store,
        document,
        max_chunk_chars=256,
        overlap_chars=0,
    )

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    location = result.location_by_chunk_id[chunk.id]
    assert location.source_path_or_url == document.metadata["original_path"]
    assert location.page == 1
    assert location.heading == "Incident Runbook"
    assert location.section == "Overview"
    assert [
        (segment.page, segment.heading, segment.section, segment.metadata)
        for segment in location.segments
    ] == [
        (1, "Incident Runbook", "Overview", {"kind": "heading"}),
        (
            2,
            "Incident Runbook",
            "Recovery",
            {"kind": "paragraph", "bbox": [1, 2, 3, 4]},
        ),
    ]
    assert store.list_chunks(profile, document.id) == [chunk]


def test_reingesting_unchanged_content_preserves_chunk_ids(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    chunk_document, _ = _chunking_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    parsed_path = tmp_path / "parsed" / "stable.txt"
    parsed_path.parent.mkdir()
    parsed_path.write_text(
        "Stable content should keep the same deterministic chunk identity.\n",
        encoding="utf-8",
    )
    first_document = _document(profile, parsed_path, document_id="doc-stable")
    reingested_document = Document(
        **{
            **first_document.to_dict(),
            "updated_at": "2026-06-04T12:05:00+00:00",
        }
    )

    store.upsert_document(profile, first_document)
    first = chunk_document(profile, store, first_document, max_chunk_chars=48)
    store.upsert_document(profile, reingested_document)
    second = chunk_document(profile, store, reingested_document, max_chunk_chars=48)

    assert [chunk.id for chunk in second.chunks] == [chunk.id for chunk in first.chunks]
    assert store.list_chunks(profile, reingested_document.id) == list(second.chunks)


def test_chunks_are_profile_scoped_when_document_ids_match(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    chunk_document, _ = _chunking_api()
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
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    text = "Shared document ids should still produce profile-scoped chunks.\n"

    work_path = tmp_path / "work-parsed.txt"
    personal_path = tmp_path / "personal-parsed.txt"
    work_path.write_text(text, encoding="utf-8")
    personal_path.write_text(text, encoding="utf-8")
    work_document = _document(work, work_path, document_id="shared-doc")
    personal_document = _document(personal, personal_path, document_id="shared-doc")
    store.upsert_document(work, work_document)
    store.upsert_document(personal, personal_document)

    work_result = chunk_document(work, store, work_document)
    personal_result = chunk_document(personal, store, personal_document)

    assert store.list_chunks(work, "shared-doc") == list(work_result.chunks)
    assert store.list_chunks(personal, "shared-doc") == list(personal_result.chunks)
    assert {chunk.id for chunk in work_result.chunks}.isdisjoint(
        {chunk.id for chunk in personal_result.chunks}
    )
