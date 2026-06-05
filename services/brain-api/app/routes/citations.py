"""Citation routes for profile-scoped Brain API RAG anchors."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query

from app.deps import get_profile_context, get_rag_store
from zsper.brain.api import ApiError, ApiProfileContext
from zsper.rag import (
    CitationAnchor,
    CitationError,
    Document,
    DocumentChunk,
    ProfileRagStore,
    inspect_citation_source,
)
from zsper.rag.citations import DEFAULT_CONTEXT_CHARS


router = APIRouter(prefix="/api/citations", tags=["citations"])


@dataclass(frozen=True)
class _CitationRecord:
    document: Document
    anchor: CitationAnchor


@router.get("")
def list_citations(
    document_id: str | None = None,
    context: ApiProfileContext = Depends(get_profile_context),
    store: ProfileRagStore = Depends(get_rag_store),
) -> dict[str, object]:
    if document_id is None:
        records = _list_citation_records(context, store)
        citations = [record.anchor for record in records]
    else:
        document = _require_document(context, store, document_id)
        citations = store.list_citation_anchors(context.profile, document.id)

    response: dict[str, object] = {
        "profile_id": context.profile_id,
        "citation_anchor_ids": [citation.id for citation in citations],
        "citations": [
            _citation_payload(context.profile_id, citation)
            for citation in citations
        ],
    }
    if document_id is not None:
        response["document_id"] = document_id
    return response


@router.get("/{citation_anchor_id}")
def get_citation(
    citation_anchor_id: str,
    context: ApiProfileContext = Depends(get_profile_context),
    store: ProfileRagStore = Depends(get_rag_store),
) -> dict[str, object]:
    record = _require_citation_record(context, store, citation_anchor_id)
    return {
        "profile_id": context.profile_id,
        "document_id": record.anchor.document_id,
        "chunk_id": record.anchor.chunk_id,
        "citation_anchor_id": record.anchor.id,
        "citation": _citation_payload(context.profile_id, record.anchor),
    }


@router.get("/{citation_anchor_id}/inspect")
def inspect_citation(
    citation_anchor_id: str,
    context_chars: int = Query(DEFAULT_CONTEXT_CHARS, ge=0),
    context: ApiProfileContext = Depends(get_profile_context),
    store: ProfileRagStore = Depends(get_rag_store),
) -> dict[str, object]:
    record = _require_citation_record(context, store, citation_anchor_id)
    try:
        source_context = inspect_citation_source(
            context.profile,
            store,
            record.document,
            record.anchor.id,
            context_chars=context_chars,
        )
    except CitationError as exc:
        raise ApiError(
            code="citation_inspection_failed",
            message=str(exc),
            status_code=400,
            profile_id=context.profile_id,
            details={
                "document_id": record.document.id,
                "citation_anchor_id": record.anchor.id,
            },
        ) from exc

    return {
        "profile_id": context.profile_id,
        "document_id": record.anchor.document_id,
        "chunk_id": record.anchor.chunk_id,
        "citation_anchor_id": record.anchor.id,
        "citation": _citation_payload(context.profile_id, source_context.anchor),
        "chunk": _chunk_payload(context.profile_id, source_context.chunk),
        "context": {
            "source_path_or_url": source_context.source_path_or_url,
            "display_range": source_context.display_range,
            "text": source_context.text,
            "citation_text": source_context.citation_text,
            "context_start_byte": source_context.context_start_byte,
            "context_end_byte": source_context.context_end_byte,
            "citation_start_byte": source_context.citation_start_byte,
            "citation_end_byte": source_context.citation_end_byte,
        },
    }


def _require_document(
    context: ApiProfileContext,
    store: ProfileRagStore,
    document_id: str,
) -> Document:
    document = store.get_document(context.profile, document_id)
    if document is None:
        raise ApiError(
            code="document_not_found",
            message="document does not exist for this profile",
            status_code=404,
            profile_id=context.profile_id,
            details={"document_id": document_id},
        )
    return document


def _require_citation_record(
    context: ApiProfileContext,
    store: ProfileRagStore,
    citation_anchor_id: str,
) -> _CitationRecord:
    for record in _list_citation_records(context, store):
        if record.anchor.id == citation_anchor_id:
            return record
    raise ApiError(
        code="citation_anchor_not_found",
        message="citation anchor does not exist for this profile",
        status_code=404,
        profile_id=context.profile_id,
        details={"citation_anchor_id": citation_anchor_id},
    )


def _list_citation_records(
    context: ApiProfileContext,
    store: ProfileRagStore,
) -> list[_CitationRecord]:
    records: list[_CitationRecord] = []
    for document in store.list_documents(context.profile):
        records.extend(
            _CitationRecord(document=document, anchor=anchor)
            for anchor in store.list_citation_anchors(context.profile, document.id)
        )
    return records


def _citation_payload(
    profile_id: str,
    citation: CitationAnchor,
) -> dict[str, object]:
    payload = citation.to_dict()
    payload["profile_id"] = profile_id
    payload["citation_anchor_id"] = citation.id
    return payload


def _chunk_payload(profile_id: str, chunk: DocumentChunk) -> dict[str, object]:
    payload = chunk.to_dict()
    payload["profile_id"] = profile_id
    payload["chunk_id"] = chunk.id
    return payload
