"""Deterministic chunking for parsed RAG document representations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zsper.profiles import Profile
from zsper.rag.models import Document, DocumentChunk
from zsper.rag.repo import REPO_PARSED_SCHEMA
from zsper.rag.store import ProfileRagStore


DOCLING_PARSED_SCHEMA: Final[str] = "zsper.rag.docling_parsed.v1"
DEFAULT_MAX_CHUNK_CHARS: Final[int] = 1200
DEFAULT_OVERLAP_CHARS: Final[int] = 0


class ChunkingError(ValueError):
    """Raised when parsed document content cannot be chunked."""


@dataclass(frozen=True)
class ChunkSourceLocation:
    """Parser-provided source location that overlaps a persisted chunk."""

    page: int | None
    heading: str | None
    section: str | None
    metadata: dict[str, Any]
    byte_start: int | None
    byte_end: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ChunkLocationMetadata:
    """Citation sidecar metadata for a persisted chunk."""

    chunk_id: str
    parser: str
    source_path_or_url: str
    byte_start: int | None
    byte_end: int | None
    page: int | None
    heading: str | None
    section: str | None
    metadata: dict[str, Any]
    segments: tuple[ChunkSourceLocation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "segments", tuple(self.segments))


@dataclass(frozen=True)
class ChunkingResult:
    """Persisted chunks plus non-canonical location metadata sidecars."""

    document_id: str
    chunks: tuple[DocumentChunk, ...]
    locations: tuple[ChunkLocationMetadata, ...]

    @property
    def location_metadata(self) -> tuple[ChunkLocationMetadata, ...]:
        return self.locations

    @property
    def location_by_chunk_id(self) -> dict[str, ChunkLocationMetadata]:
        return {location.chunk_id: location for location in self.locations}

    @property
    def location_metadata_by_chunk_id(self) -> dict[str, ChunkLocationMetadata]:
        return self.location_by_chunk_id


@dataclass(frozen=True)
class _ParsedSegment:
    text: str
    page: int | None
    heading: str | None
    section: str | None
    metadata: dict[str, Any]
    char_start: int | None
    char_end: int | None


@dataclass(frozen=True)
class _ParsedRepresentation:
    text: str
    parser: str
    content_fingerprint: str
    segments: tuple[_ParsedSegment, ...]


@dataclass(frozen=True)
class _ChunkSpan:
    text: str
    char_start: int
    char_end: int


def chunk_document(
    profile: Profile,
    store: ProfileRagStore,
    document: Document,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> ChunkingResult:
    """Convert a parsed representation into stable, profile-scoped chunks."""

    if document.profile_id != profile.name:
        raise ChunkingError(
            "document profile_id must match the profile used for chunking"
        )
    _validate_chunking_bounds(
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
    )

    parsed = _load_parsed_representation(document)
    spans = _chunk_text(
        parsed.text,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
    )
    if not spans:
        raise ChunkingError(f"parsed representation is empty for document {document.id}")

    chunks: list[DocumentChunk] = []
    locations: list[ChunkLocationMetadata] = []
    for index, span in enumerate(spans):
        byte_start = _byte_offset(parsed.text, span.char_start)
        byte_end = _byte_offset(parsed.text, span.char_end)
        chunk_id = _stable_id(
            "chunk",
            profile.name,
            document.id,
            document.content_hash,
            _document_version(document),
            document.parser,
            parsed.content_fingerprint,
            index,
            span.text,
        )
        chunk = DocumentChunk(
            id=chunk_id,
            document_id=document.id,
            chunk_index=index,
            text=span.text,
            citation_anchor_id=_stable_id("anchor-pending", chunk_id),
            token_estimate=_token_estimate(span.text),
            byte_start=byte_start,
            byte_end=byte_end,
            embedding_model=None,
            embedding_vector_id=None,
        )
        store.upsert_chunk(profile, chunk)
        chunks.append(chunk)
        locations.append(
            _location_metadata(
                document=document,
                parsed=parsed,
                span=span,
                chunk_id=chunk_id,
                byte_start=byte_start,
                byte_end=byte_end,
            )
        )

    return ChunkingResult(
        document_id=document.id,
        chunks=tuple(chunks),
        locations=tuple(locations),
    )


def _validate_chunking_bounds(*, max_chunk_chars: int, overlap_chars: int) -> None:
    if not isinstance(max_chunk_chars, int) or isinstance(max_chunk_chars, bool):
        raise ChunkingError("max_chunk_chars must be a positive integer")
    if max_chunk_chars <= 0:
        raise ChunkingError("max_chunk_chars must be a positive integer")
    if not isinstance(overlap_chars, int) or isinstance(overlap_chars, bool):
        raise ChunkingError("overlap_chars must be a non-negative integer")
    if overlap_chars < 0:
        raise ChunkingError("overlap_chars must be a non-negative integer")
    if overlap_chars >= max_chunk_chars:
        raise ChunkingError("overlap_chars must be smaller than max_chunk_chars")


def _load_parsed_representation(document: Document) -> _ParsedRepresentation:
    parsed_path = Path(document.parsed_representation_path)
    try:
        raw_bytes = parsed_path.read_bytes()
    except OSError as exc:
        raise ChunkingError(
            f"could not read parsed representation for document {document.id}: "
            f"{parsed_path}"
        ) from exc

    if document.parser == "docling":
        return _load_docling_representation(document, raw_bytes)
    if document.parser == "repo":
        return _load_repo_representation(document, raw_bytes)
    return _load_text_representation(document, raw_bytes)


def _load_text_representation(
    document: Document,
    raw_bytes: bytes,
) -> _ParsedRepresentation:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ChunkingError(
            f"parsed representation for document {document.id} is not utf-8 text"
        ) from exc
    return _ParsedRepresentation(
        text=text,
        parser=document.parser,
        content_fingerprint=_content_fingerprint(
            {"parser": document.parser, "text": text}
        ),
        segments=(),
    )


def _load_docling_representation(
    document: Document,
    raw_bytes: bytes,
) -> _ParsedRepresentation:
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChunkingError(
            f"Docling parsed representation is invalid JSON for document {document.id}"
        ) from exc
    if not isinstance(data, dict):
        raise ChunkingError("Docling parsed representation must be a JSON object")
    if data.get("schema") != DOCLING_PARSED_SCHEMA:
        raise ChunkingError(
            "Docling parsed representation schema must be "
            f"{DOCLING_PARSED_SCHEMA}"
        )
    parsed_document_id = data.get("document_id")
    if parsed_document_id is not None and parsed_document_id != document.id:
        raise ChunkingError(
            "Docling parsed representation document_id must match the document"
        )
    text = data.get("text")
    if not isinstance(text, str):
        raise ChunkingError("Docling parsed representation text must be a string")

    segments = _structured_segments(data.get("segments"), text, label="Docling")
    return _ParsedRepresentation(
        text=text,
        parser="docling",
        content_fingerprint=_content_fingerprint(
            {
                "parser": "docling",
                "text": text,
                "segments": [_segment_fingerprint(segment) for segment in segments],
            }
        ),
        segments=segments,
    )


def _load_repo_representation(
    document: Document,
    raw_bytes: bytes,
) -> _ParsedRepresentation:
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChunkingError(
            f"Repo parsed representation is invalid JSON for document {document.id}"
        ) from exc
    if not isinstance(data, dict):
        raise ChunkingError("Repo parsed representation must be a JSON object")
    if data.get("schema") != REPO_PARSED_SCHEMA:
        raise ChunkingError(
            "Repo parsed representation schema must be "
            f"{REPO_PARSED_SCHEMA}"
        )
    parsed_document_id = data.get("document_id")
    if parsed_document_id is not None and parsed_document_id != document.id:
        raise ChunkingError(
            "Repo parsed representation document_id must match the document"
        )
    text = data.get("text")
    if not isinstance(text, str):
        raise ChunkingError("Repo parsed representation text must be a string")

    segments = _structured_segments(data.get("segments"), text, label="Repo")
    return _ParsedRepresentation(
        text=text,
        parser="repo",
        content_fingerprint=_content_fingerprint(
            {
                "parser": "repo",
                "text": text,
                "segments": [_segment_fingerprint(segment) for segment in segments],
            }
        ),
        segments=segments,
    )


def _structured_segments(
    raw_segments: Any,
    text: str,
    *,
    label: str,
) -> tuple[_ParsedSegment, ...]:
    if raw_segments is None:
        return ()
    if not isinstance(raw_segments, list):
        raise ChunkingError(f"{label} parsed representation segments must be a list")

    segments: list[_ParsedSegment] = []
    cursor = 0
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise ChunkingError(f"{label} segment must be a JSON object")
        segment_text = raw_segment.get("text")
        if not isinstance(segment_text, str) or not segment_text:
            continue
        char_start = text.find(segment_text, cursor)
        if char_start < 0:
            char_start = text.find(segment_text)
        char_end: int | None
        if char_start >= 0:
            char_end = char_start + len(segment_text)
            cursor = char_end
        else:
            char_start = None
            char_end = None
        metadata = raw_segment.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ChunkingError(f"{label} segment metadata must be a JSON object")
        segments.append(
            _ParsedSegment(
                text=segment_text,
                page=_as_int(raw_segment.get("page")),
                heading=_as_non_empty_str(raw_segment.get("heading")),
                section=_as_non_empty_str(raw_segment.get("section")),
                metadata=dict(metadata),
                char_start=char_start,
                char_end=char_end,
            )
        )
    return tuple(segments)


def _segment_fingerprint(segment: _ParsedSegment) -> dict[str, Any]:
    return {
        "text": segment.text,
        "page": segment.page,
        "heading": segment.heading,
        "section": segment.section,
        "metadata": segment.metadata,
    }


def _chunk_text(
    text: str,
    *,
    max_chunk_chars: int,
    overlap_chars: int,
) -> tuple[_ChunkSpan, ...]:
    spans: list[_ChunkSpan] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        while start < text_length and text[start].isspace():
            start += 1
        if start >= text_length:
            break

        hard_end = min(start + max_chunk_chars, text_length)
        end = hard_end
        if hard_end < text_length:
            end = _best_boundary(text, start, hard_end)

        chunk_start, chunk_end = _trim_span(text, start, end)
        if chunk_start < chunk_end:
            spans.append(
                _ChunkSpan(
                    text=text[chunk_start:chunk_end],
                    char_start=chunk_start,
                    char_end=chunk_end,
                )
            )

        if hard_end >= text_length:
            break
        next_start = end - overlap_chars
        if next_start <= start:
            next_start = end
        start = next_start
    return tuple(spans)


def _best_boundary(text: str, start: int, hard_end: int) -> int:
    lower_bound = start + max(1, (hard_end - start) // 2)
    candidates = (
        text.rfind("\n\n", start, hard_end),
        text.rfind("\n", start, hard_end),
        _sentence_boundary(text, start, hard_end),
        text.rfind(" ", start, hard_end),
    )
    for candidate in candidates:
        if candidate >= lower_bound:
            return candidate
    return hard_end


def _sentence_boundary(text: str, start: int, hard_end: int) -> int:
    period_index = text.rfind(". ", start, hard_end)
    if period_index < 0:
        return -1
    return period_index + 1


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _location_metadata(
    *,
    document: Document,
    parsed: _ParsedRepresentation,
    span: _ChunkSpan,
    chunk_id: str,
    byte_start: int,
    byte_end: int,
) -> ChunkLocationMetadata:
    segment_locations = tuple(
        _source_location(parsed.text, segment)
        for segment in parsed.segments
        if _overlaps(span, segment)
    )
    first_segment = segment_locations[0] if segment_locations else None
    return ChunkLocationMetadata(
        chunk_id=chunk_id,
        parser=parsed.parser,
        source_path_or_url=_source_path_or_url(document, first_segment),
        byte_start=byte_start,
        byte_end=byte_end,
        page=first_segment.page if first_segment is not None else None,
        heading=first_segment.heading if first_segment is not None else None,
        section=first_segment.section if first_segment is not None else None,
        metadata=first_segment.metadata if first_segment is not None else {},
        segments=segment_locations,
    )


def _source_location(text: str, segment: _ParsedSegment) -> ChunkSourceLocation:
    byte_start: int | None = None
    byte_end: int | None = None
    if segment.char_start is not None and segment.char_end is not None:
        byte_start = _byte_offset(text, segment.char_start)
        byte_end = _byte_offset(text, segment.char_end)
    return ChunkSourceLocation(
        page=segment.page,
        heading=segment.heading,
        section=segment.section,
        metadata=segment.metadata,
        byte_start=byte_start,
        byte_end=byte_end,
    )


def _overlaps(span: _ChunkSpan, segment: _ParsedSegment) -> bool:
    if segment.char_start is None or segment.char_end is None:
        return False
    return segment.char_start < span.char_end and segment.char_end > span.char_start


def _source_path_or_url(
    document: Document,
    location: ChunkSourceLocation | None,
) -> str:
    if location is not None:
        for key in ("source_path_or_url", "original_url", "final_url", "original_path"):
            value = location.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
    for key in ("original_url", "final_url", "original_path"):
        value = document.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return document.raw_asset_path


def _document_version(document: Document) -> str:
    version = document.metadata.get("version")
    if isinstance(version, bool):
        return "unknown"
    if isinstance(version, int):
        return str(version)
    if isinstance(version, str) and version.strip():
        return version.strip()
    return "unknown"


def _token_estimate(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _byte_offset(text: str, char_index: int) -> int:
    return len(text[:char_index].encode("utf-8"))


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(b"\0")
        digest.update(
            json.dumps(part, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
    return f"{prefix}-{digest.hexdigest()[:24]}"


def _content_fingerprint(payload: dict[str, Any]) -> str:
    return _stable_id("parsed", payload)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _as_non_empty_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


__all__ = [
    "ChunkLocationMetadata",
    "ChunkSourceLocation",
    "ChunkingError",
    "ChunkingResult",
    "chunk_document",
]
