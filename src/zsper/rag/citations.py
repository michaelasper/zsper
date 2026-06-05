"""Citation anchor generation and source inspection for RAG chunks."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from zsper.profiles import Profile
from zsper.rag.chunking import ChunkingResult, ChunkLocationMetadata
from zsper.rag.models import CitationAnchor, Document, DocumentChunk
from zsper.rag.store import ProfileRagStore


DEFAULT_CONTEXT_CHARS = 240


class CitationError(ValueError):
    """Raised when citation anchors cannot be generated or inspected."""


@dataclass(frozen=True)
class CitationAnchorResult:
    """Citation anchors generated for a document."""

    document_id: str
    anchors: tuple[CitationAnchor, ...]

    @property
    def anchor_by_chunk_id(self) -> dict[str, CitationAnchor]:
        return {anchor.chunk_id: anchor for anchor in self.anchors}

    @property
    def anchor_by_id(self) -> dict[str, CitationAnchor]:
        return {anchor.id: anchor for anchor in self.anchors}


@dataclass(frozen=True)
class CitationSourceContext:
    """Bounded source text around a citation anchor."""

    anchor: CitationAnchor
    chunk: DocumentChunk
    source_path_or_url: str
    display_range: str | None
    text: str
    citation_text: str
    context_start_byte: int
    context_end_byte: int
    citation_start_byte: int
    citation_end_byte: int


def generate_citation_anchors(
    profile: Profile,
    store: ProfileRagStore,
    document: Document,
    chunks_or_result: ChunkingResult | Iterable[DocumentChunk],
) -> CitationAnchorResult:
    """Create one first-class citation anchor for each stored chunk."""

    stored_document = _require_profile_document(profile, store, document)
    _provided_chunks, locations = _normalize_chunks_or_result(chunks_or_result)
    stored_chunks = tuple(store.list_chunks(profile, stored_document.id))
    if not stored_chunks:
        raise CitationError(f"document has no stored chunks: {stored_document.id}")

    anchors: list[CitationAnchor] = []
    for chunk in stored_chunks:
        location = locations.get(chunk.id)
        anchor = CitationAnchor(
            id=chunk.citation_anchor_id,
            document_id=stored_document.id,
            chunk_id=chunk.id,
            label=_anchor_label(stored_document, chunk, location),
            source_path_or_url=_source_path_or_url(stored_document, location),
            display_range=_display_range(chunk, location),
        )
        store.upsert_citation_anchor(profile, anchor)
        anchors.append(anchor)

    _require_exactly_one_anchor_per_chunk(
        profile=profile,
        store=store,
        document_id=stored_document.id,
        chunks=stored_chunks,
    )
    return CitationAnchorResult(
        document_id=stored_document.id,
        anchors=tuple(anchors),
    )


def inspect_citation_source(
    profile: Profile,
    store: ProfileRagStore,
    document: Document,
    anchor_id: str,
    context_chars: int = DEFAULT_CONTEXT_CHARS,
) -> CitationSourceContext:
    """Return bounded parsed-source text around a citation anchor."""

    stored_document = _require_profile_document(profile, store, document)
    _require_context_chars(context_chars)
    anchor = _find_anchor(profile, store, stored_document.id, anchor_id)
    chunk = _find_chunk(profile, store, stored_document.id, anchor)
    source_text = _load_source_text(profile, stored_document)
    citation_start, citation_end = _citation_char_range(source_text, chunk)

    context_start = max(0, citation_start - context_chars)
    context_end = min(len(source_text), citation_end + context_chars)
    return CitationSourceContext(
        anchor=anchor,
        chunk=chunk,
        source_path_or_url=anchor.source_path_or_url,
        display_range=anchor.display_range,
        text=source_text[context_start:context_end],
        citation_text=source_text[citation_start:citation_end],
        context_start_byte=_byte_offset(source_text, context_start),
        context_end_byte=_byte_offset(source_text, context_end),
        citation_start_byte=_byte_offset(source_text, citation_start),
        citation_end_byte=_byte_offset(source_text, citation_end),
    )


def _require_profile_document(
    profile: Profile,
    store: ProfileRagStore,
    document: Document,
) -> Document:
    if document.profile_id != profile.name:
        raise CitationError("document profile_id must match the profile")
    stored_document = store.get_document(profile, document.id)
    if stored_document is None:
        raise CitationError(
            f"document does not exist for profile {profile.name}: {document.id}"
        )
    return stored_document


def _normalize_chunks_or_result(
    chunks_or_result: ChunkingResult | Iterable[DocumentChunk],
) -> tuple[tuple[DocumentChunk, ...], dict[str, ChunkLocationMetadata]]:
    if isinstance(chunks_or_result, ChunkingResult):
        return (
            tuple(chunks_or_result.chunks),
            dict(chunks_or_result.location_by_chunk_id),
        )
    try:
        chunks = tuple(chunks_or_result)
    except TypeError as exc:
        raise CitationError("chunks_or_result must be a ChunkingResult or chunks") from exc
    return chunks, {}


def _anchor_label(
    document: Document,
    chunk: DocumentChunk,
    location: ChunkLocationMetadata | None,
) -> str:
    label = document.title
    if location is not None and location.page is not None:
        label = f"{label} p. {location.page}"
    else:
        label = f"{label} chunk {chunk.chunk_index + 1}"

    location_parts: list[str] = []
    if location is not None:
        for value in (location.heading, location.section):
            if value is not None and value not in location_parts:
                location_parts.append(value)
    if location_parts:
        label = f"{label} - {' / '.join(location_parts)}"
    return label


def _source_path_or_url(
    document: Document,
    location: ChunkLocationMetadata | None,
) -> str:
    if location is not None and location.source_path_or_url.strip():
        return location.source_path_or_url
    for key in ("original_url", "final_url", "original_path"):
        value = document.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return document.raw_asset_path


def _display_range(
    chunk: DocumentChunk,
    location: ChunkLocationMetadata | None,
) -> str | None:
    parts: list[str] = []
    if location is not None and location.page is not None:
        parts.append(f"page {location.page}")
    byte_start = location.byte_start if location is not None else chunk.byte_start
    byte_end = location.byte_end if location is not None else chunk.byte_end
    if byte_start is not None and byte_end is not None:
        parts.append(f"bytes {byte_start}-{byte_end}")
    return ", ".join(parts) if parts else None


def _require_exactly_one_anchor_per_chunk(
    *,
    profile: Profile,
    store: ProfileRagStore,
    document_id: str,
    chunks: tuple[DocumentChunk, ...],
) -> None:
    anchors_by_chunk_id: dict[str, list[CitationAnchor]] = {
        chunk.id: [] for chunk in chunks
    }
    for anchor in store.list_citation_anchors(profile, document_id):
        if anchor.chunk_id in anchors_by_chunk_id:
            anchors_by_chunk_id[anchor.chunk_id].append(anchor)

    bad_chunk_ids = [
        chunk_id
        for chunk_id, anchors in anchors_by_chunk_id.items()
        if len(anchors) != 1
    ]
    if bad_chunk_ids:
        raise CitationError(
            "every stored chunk must have exactly one citation anchor: "
            f"{', '.join(sorted(bad_chunk_ids))}"
        )


def _require_context_chars(context_chars: int) -> None:
    if (
        not isinstance(context_chars, int)
        or isinstance(context_chars, bool)
        or context_chars < 0
    ):
        raise CitationError("context_chars must be a non-negative integer")


def _find_anchor(
    profile: Profile,
    store: ProfileRagStore,
    document_id: str,
    anchor_id: str,
) -> CitationAnchor:
    for anchor in store.list_citation_anchors(profile, document_id):
        if anchor.id == anchor_id:
            return anchor
    raise CitationError(f"citation anchor does not exist: {anchor_id}")


def _find_chunk(
    profile: Profile,
    store: ProfileRagStore,
    document_id: str,
    anchor: CitationAnchor,
) -> DocumentChunk:
    for chunk in store.list_chunks(profile, document_id):
        if chunk.id == anchor.chunk_id:
            if chunk.citation_anchor_id != anchor.id:
                raise CitationError(
                    "citation anchor id does not match the stored chunk"
                )
            return chunk
    raise CitationError(f"citation chunk does not exist: {anchor.chunk_id}")


def _load_source_text(profile: Profile, document: Document) -> str:
    parsed_path = _validated_parsed_source_path(profile, document)
    try:
        raw_bytes = parsed_path.read_bytes()
    except OSError as exc:
        raise CitationError(
            "could not read parsed source for document "
            f"{document.id}: {parsed_path}"
        ) from exc

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CitationError(
            f"parsed source is not utf-8 for document {document.id}"
        ) from exc

    if document.parser != "docling":
        return raw_text
    return _docling_source_text(document, raw_text)


def _validated_parsed_source_path(profile: Profile, document: Document) -> Path:
    parsed_root = (
        Path(profile.root).expanduser() / "brain" / "parsed"
    ).resolve(strict=False)
    parsed_path = Path(document.parsed_representation_path).expanduser()
    resolved_path = parsed_path.resolve(strict=False)
    if not resolved_path.is_relative_to(parsed_root):
        raise CitationError(
            "parsed source path must be inside the active profile "
            f"brain/parsed directory for profile {profile.name}: {parsed_path}"
        )
    return resolved_path


def _docling_source_text(document: Document, raw_text: str) -> str:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CitationError(
            f"Docling parsed source is invalid JSON for document {document.id}"
        ) from exc
    if not isinstance(data, dict):
        raise CitationError("Docling parsed source must be a JSON object")
    text = data.get("text")
    if not isinstance(text, str):
        raise CitationError("Docling parsed source text must be a string")
    return text


def _citation_char_range(text: str, chunk: DocumentChunk) -> tuple[int, int]:
    if chunk.byte_start is not None and chunk.byte_end is not None:
        start = _char_index_for_byte_offset(text, chunk.byte_start)
        end = _char_index_for_byte_offset(text, chunk.byte_end)
        if start is not None and end is not None and start <= end:
            return start, end

    start = text.find(chunk.text)
    if start < 0:
        raise CitationError(
            f"chunk text could not be located in source: {chunk.id}"
        )
    return start, start + len(chunk.text)


def _char_index_for_byte_offset(text: str, byte_offset: int) -> int | None:
    encoded = text.encode("utf-8")
    if byte_offset < 0 or byte_offset > len(encoded):
        return None
    try:
        return len(encoded[:byte_offset].decode("utf-8"))
    except UnicodeDecodeError:
        return None


def _byte_offset(text: str, char_index: int) -> int:
    return len(text[:char_index].encode("utf-8"))


__all__ = [
    "CitationAnchorResult",
    "CitationError",
    "CitationSourceContext",
    "generate_citation_anchors",
    "inspect_citation_source",
]
