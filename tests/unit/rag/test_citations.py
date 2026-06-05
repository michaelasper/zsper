import json
from pathlib import Path
from typing import Any

import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag import Document, DocumentChunk, ProfileRagStore, chunk_document


def _citation_api() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from zsper.rag.citations import (
            CitationAnchorResult,
            CitationError,
            CitationSourceContext,
            generate_citation_anchors,
            inspect_citation_source,
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"citation API is missing: {exc}")
    return (
        generate_citation_anchors,
        inspect_citation_source,
        CitationAnchorResult,
        CitationSourceContext,
        CitationError,
    )


def _document(
    profile: Profile,
    parsed_path: Path,
    *,
    document_id: str = "doc-1",
    parser: str = "text",
    content_hash: str = "sha256:fixture",
    metadata: dict[str, Any] | None = None,
) -> Document:
    return Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(parsed_path.with_suffix(".raw")),
        parsed_representation_path=str(parsed_path),
        title="Citation Fixture",
        metadata={
            "original_path": str(parsed_path.with_suffix(".source")),
            "source_filename": parsed_path.name,
            "version": 1,
            **(metadata or {}),
        },
        content_hash=content_hash,
        parser=parser,
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def test_generate_citation_anchors_persists_one_anchor_per_stored_chunk(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    generate_citation_anchors, _, result_type, _, _ = _citation_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    parsed_path = tmp_path / "parsed" / "incident.txt"
    parsed_path.parent.mkdir()
    parsed_path.write_text(
        (
            "# Incident Notes\n\n"
            "Operators restart the profile-local worker from runtime state.\n\n"
            "They verify exact commands, paths, and status before closing work.\n"
        ),
        encoding="utf-8",
    )
    document = _document(profile, parsed_path)
    store.upsert_document(profile, document)
    chunking_result = chunk_document(profile, store, document, max_chunk_chars=64)

    result = generate_citation_anchors(profile, store, document, chunking_result)

    stored_chunks = store.list_chunks(profile, document.id)
    stored_anchors = store.list_citation_anchors(profile, document.id)
    assert isinstance(result, result_type)
    assert len(stored_anchors) == len(stored_chunks) == len(result.anchors)
    assert {anchor.chunk_id for anchor in stored_anchors} == {
        chunk.id for chunk in stored_chunks
    }
    assert [result.anchor_by_chunk_id[chunk.id].id for chunk in stored_chunks] == [
        chunk.citation_anchor_id for chunk in stored_chunks
    ]
    assert len({anchor.chunk_id for anchor in stored_anchors}) == len(stored_chunks)
    assert all(
        anchor.source_path_or_url == document.metadata["original_path"]
        for anchor in stored_anchors
    )
    assert all(anchor.display_range is not None for anchor in stored_anchors)
    assert not hasattr(result.anchors[0], "answer_confidence")


def test_generate_citation_anchors_uses_chunk_location_metadata_for_labels_and_ranges(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    generate_citation_anchors, _, _, _, _ = _citation_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    parsed_path = tmp_path / "parsed" / "runbook.json"
    parsed_path.parent.mkdir()
    text = "# Runbook\n\nRestart the worker from the profile runtime directory."
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
                        "text": "# Runbook",
                        "page": 1,
                        "heading": "Runbook",
                        "section": "Overview",
                        "metadata": {"kind": "heading"},
                    },
                    {
                        "index": 1,
                        "text": "Restart the worker from the profile runtime directory.",
                        "page": 2,
                        "heading": "Runbook",
                        "section": "Recovery",
                        "metadata": {"kind": "paragraph"},
                    },
                ],
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
        content_hash="sha256:docling-fixture",
    )
    store.upsert_document(profile, document)
    chunking_result = chunk_document(profile, store, document, max_chunk_chars=256)

    result = generate_citation_anchors(profile, store, document, chunking_result)

    assert len(result.anchors) == 1
    anchor = result.anchors[0]
    assert anchor.id == chunking_result.chunks[0].citation_anchor_id
    assert anchor.label == "Citation Fixture p. 1 - Runbook / Overview"
    assert anchor.display_range == (
        f"page 1, bytes {chunking_result.chunks[0].byte_start}-"
        f"{chunking_result.chunks[0].byte_end}"
    )


def test_inspect_citation_source_returns_bounded_source_text(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    generate_citation_anchors, inspect_citation_source, _, context_type, _ = _citation_api()
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    parsed_path = Path(profile.root) / "brain" / "parsed" / "source.txt"
    parsed_path.write_text(
        "aaaaabbbbbTARGET-CHUNKcccccddddd",
        encoding="utf-8",
    )
    document = _document(profile, parsed_path)
    target_chunk = DocumentChunk(
        id="chunk-target",
        document_id=document.id,
        chunk_index=0,
        text="TARGET-CHUNK",
        citation_anchor_id="anchor-target",
        token_estimate=3,
        byte_start=10,
        byte_end=22,
        embedding_model=None,
        embedding_vector_id=None,
    )
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, target_chunk)
    generate_citation_anchors(profile, store, document, [target_chunk])

    context = inspect_citation_source(
        profile,
        store,
        document,
        target_chunk.citation_anchor_id,
        context_chars=3,
    )

    assert isinstance(context, context_type)
    assert context.anchor.id == target_chunk.citation_anchor_id
    assert context.chunk.id == target_chunk.id
    assert context.text == "bbbTARGET-CHUNKccc"
    assert context.citation_text == "TARGET-CHUNK"
    assert len(context.text) <= len(target_chunk.text) + 6
    assert not hasattr(context, "answer_confidence")


def test_citation_anchors_and_source_context_are_profile_isolated(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    generate_citation_anchors, inspect_citation_source, _, _, citation_error = _citation_api()
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
    work_path = Path(work.root) / "brain" / "parsed" / "work-parsed.txt"
    personal_path = Path(personal.root) / "brain" / "parsed" / "personal-parsed.txt"
    work_path.write_text("work-only citation context\n", encoding="utf-8")
    personal_path.write_text("personal-only citation context\n", encoding="utf-8")
    work_document = _document(work, work_path, document_id="shared-doc")
    personal_document = _document(personal, personal_path, document_id="shared-doc")
    store.upsert_document(work, work_document)
    store.upsert_document(personal, personal_document)
    work_result = chunk_document(work, store, work_document)
    personal_result = chunk_document(personal, store, personal_document)

    generate_citation_anchors(work, store, work_document, work_result)
    generate_citation_anchors(personal, store, personal_document, personal_result)

    work_anchor = store.list_citation_anchors(work, "shared-doc")[0]
    personal_anchor = store.list_citation_anchors(personal, "shared-doc")[0]
    assert work_anchor.id != personal_anchor.id
    assert "work-only" in inspect_citation_source(
        work,
        store,
        work_document,
        work_anchor.id,
    ).text
    assert "personal-only" in inspect_citation_source(
        personal,
        store,
        personal_document,
        personal_anchor.id,
    ).text
    with pytest.raises(citation_error, match="document profile_id must match"):
        inspect_citation_source(personal, store, work_document, work_anchor.id)
    with pytest.raises(citation_error, match="citation anchor does not exist"):
        inspect_citation_source(work, store, work_document, personal_anchor.id)


def test_inspect_citation_source_rejects_cross_profile_parsed_path(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    generate_citation_anchors, inspect_citation_source, _, _, citation_error = _citation_api()
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
    personal_parsed_path = Path(personal.root) / "brain" / "parsed" / "private.txt"
    personal_parsed_path.write_text(
        "personal-only secret citation context\n",
        encoding="utf-8",
    )
    work_document = _document(
        work,
        personal_parsed_path,
        document_id="work-doc-with-cross-profile-source",
    )
    target_chunk = DocumentChunk(
        id="chunk-cross-profile",
        document_id=work_document.id,
        chunk_index=0,
        text="personal-only secret",
        citation_anchor_id="anchor-cross-profile",
        token_estimate=3,
        byte_start=0,
        byte_end=20,
        embedding_model=None,
        embedding_vector_id=None,
    )
    store.upsert_document(work, work_document)
    store.upsert_chunk(work, target_chunk)
    generate_citation_anchors(work, store, work_document, [target_chunk])

    with pytest.raises(citation_error, match="parsed source path"):
        inspect_citation_source(
            work,
            store,
            work_document,
            target_chunk.citation_anchor_id,
        )
