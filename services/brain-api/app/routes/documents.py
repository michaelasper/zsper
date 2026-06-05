"""Document routes for profile-scoped Brain API RAG records."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_profile_context, get_rag_store
from zsper.brain.api import ApiError, ApiProfileContext
from zsper.rag import CitationAnchor, Document, DocumentChunk, ProfileRagStore
from zsper.security.redaction import redact_secrets


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(
    context: ApiProfileContext = Depends(get_profile_context),
    store: ProfileRagStore = Depends(get_rag_store),
) -> dict[str, object]:
    documents = store.list_documents(context.profile)
    return {
        "profile_id": context.profile_id,
        "document_ids": [document.id for document in documents],
        "documents": [_document_payload(document) for document in documents],
    }


@router.get("/{document_id}")
def get_document(
    document_id: str,
    context: ApiProfileContext = Depends(get_profile_context),
    store: ProfileRagStore = Depends(get_rag_store),
) -> dict[str, object]:
    document = _require_document(context, store, document_id)
    return {
        "profile_id": context.profile_id,
        "document_id": document.id,
        "document": _document_payload(document),
    }


@router.get("/{document_id}/inspect")
def inspect_document(
    document_id: str,
    context: ApiProfileContext = Depends(get_profile_context),
    store: ProfileRagStore = Depends(get_rag_store),
) -> dict[str, object]:
    document = _require_document(context, store, document_id)
    chunks = store.list_chunks(context.profile, document.id)
    citations = store.list_citation_anchors(context.profile, document.id)
    return {
        "profile_id": context.profile_id,
        "document_id": document.id,
        "document": _document_payload(document),
        "chunk_ids": [chunk.id for chunk in chunks],
        "citation_anchor_ids": [citation.id for citation in citations],
        "chunks": [_chunk_payload(context.profile_id, chunk) for chunk in chunks],
        "citations": [
            _citation_payload(context.profile_id, citation)
            for citation in citations
        ],
    }


def _document_payload(document: Document) -> dict[str, object]:
    payload = document.to_dict()
    payload["document_id"] = document.id
    payload["metadata"] = redact_secrets(document.metadata)
    return payload


def _chunk_payload(profile_id: str, chunk: DocumentChunk) -> dict[str, object]:
    payload = chunk.to_dict()
    payload["profile_id"] = profile_id
    payload["chunk_id"] = chunk.id
    return payload


def _citation_payload(
    profile_id: str,
    citation: CitationAnchor,
) -> dict[str, object]:
    payload = citation.to_dict()
    payload["profile_id"] = profile_id
    payload["citation_anchor_id"] = citation.id
    return payload


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
