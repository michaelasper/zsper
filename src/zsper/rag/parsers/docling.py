"""Local Docling parser adapter for complex RAG assets."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from zsper.rag.models import Document
from zsper.rag.parsers.selector import DOCLING_EXTENSIONS, DOCLING_MEDIA_TYPES


class DoclingConverter(Protocol):
    """Small protocol for fakeable Docling converters."""

    def convert(self, source: str) -> Any:
        """Convert a local file path into a Docling conversion result."""


@dataclass(frozen=True)
class ParsedDoclingSegment:
    index: int
    text: str
    page: int | None
    heading: str | None
    section: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "page": self.page,
            "heading": self.heading,
            "section": self.section,
            "metadata": _json_safe(self.metadata),
        }


@dataclass(frozen=True)
class ParsedDoclingDocument:
    document_id: str
    parser: str
    text: str
    raw_asset_path: str
    parsed_representation_path: str
    converter: str
    byte_length: int
    segments: tuple[ParsedDoclingSegment, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "zsper.rag.docling_parsed.v1",
            "document_id": self.document_id,
            "parser": self.parser,
            "text": self.text,
            "raw_asset_path": self.raw_asset_path,
            "parsed_representation_path": self.parsed_representation_path,
            "converter": self.converter,
            "byte_length": self.byte_length,
            "segments": [segment.to_dict() for segment in self.segments],
            "metadata": _json_safe(self.metadata),
        }


@dataclass(frozen=True)
class DoclingParserFailure:
    document_id: str
    parser: str
    raw_asset_path: str
    parsed_representation_path: str
    error_type: str
    reason: str
    details: str


class DoclingParserSetupError(RuntimeError):
    """Raised when the local Docling dependency cannot be constructed."""


def parse_docling_document(
    document: Document,
    *,
    converter: DoclingConverter | None = None,
) -> ParsedDoclingDocument | DoclingParserFailure:
    """Parse a Docling-routed document and write a normalized representation."""

    raw_asset_path = Path(document.raw_asset_path)
    parsed_representation_path = Path(document.parsed_representation_path)

    if document.parser != "docling":
        return _failure(
            document,
            error_type="UnsupportedDoclingRoute",
            reason=(
                "docling parser only accepts docling routes; "
                f"document {document.id} is routed to {document.parser}"
            ),
        )

    unsupported_reason = _unsupported_reason(document, raw_asset_path)
    if unsupported_reason is not None:
        return _failure(
            document,
            error_type="UnsupportedDoclingSource",
            reason=unsupported_reason,
        )

    try:
        byte_length = raw_asset_path.stat().st_size
    except OSError as exc:
        return _failure(
            document,
            error_type=type(exc).__name__,
            reason=(
                "Docling parser could not read raw asset for document "
                f"{document.id}: {raw_asset_path}"
            ),
            details=str(exc),
        )

    if converter is None:
        try:
            converter = _default_converter()
        except DoclingParserSetupError as exc:
            return _failure(
                document,
                error_type=type(exc).__name__,
                reason=str(exc),
                details=str(exc.__cause__ or exc),
            )

    try:
        result = converter.convert(str(raw_asset_path))
        docling_document = getattr(result, "document", result)
        segments = _extract_segments(docling_document)
        text = _extract_text(docling_document)
        if not text and segments:
            text = "\n\n".join(segment.text for segment in segments)
        if not segments and text:
            segments = (
                ParsedDoclingSegment(
                    index=0,
                    text=text,
                    page=None,
                    heading=None,
                    section=None,
                    metadata={},
                ),
            )
        if not text:
            return _failure(
                document,
                error_type="EmptyDoclingOutput",
                reason=f"Docling produced no text for document {document.id}",
            )

        parsed = ParsedDoclingDocument(
            document_id=document.id,
            parser="docling",
            text=text,
            raw_asset_path=str(raw_asset_path),
            parsed_representation_path=str(parsed_representation_path),
            converter=_converter_name(converter),
            byte_length=byte_length,
            segments=segments,
            metadata={
                "document_title": document.title,
                "media_type": _document_media_type(document),
                "source_filename": raw_asset_path.name,
            },
        )
        _write_parsed_representation(parsed_representation_path, parsed)
        return parsed
    except Exception as exc:
        return _failure(
            document,
            error_type=type(exc).__name__,
            reason=(
                f"Docling failed to parse document {document.id}: "
                f"{raw_asset_path}"
            ),
            details=str(exc),
        )


def _default_converter() -> DoclingConverter:
    try:
        from docling.document_converter import DocumentConverter
    except ModuleNotFoundError as exc:
        raise DoclingParserSetupError(
            "Docling is required for PDFs, Office files, and complex HTML; "
            "install the local docling package to parse this document"
        ) from exc
    return DocumentConverter()


def _unsupported_reason(document: Document, raw_asset_path: Path) -> str | None:
    media_type = _document_media_type(document)
    suffix = raw_asset_path.suffix.lower()
    if suffix in DOCLING_EXTENSIONS:
        return None
    if media_type in DOCLING_MEDIA_TYPES:
        return None
    return (
        "unsupported Docling parser input "
        f"source={str(raw_asset_path)!r}, "
        f"media_type={media_type or 'unknown'}, extension={suffix or 'none'}"
    )


def _document_media_type(document: Document) -> str | None:
    value = document.metadata.get("media_type")
    if not isinstance(value, str):
        return None
    return value.split(";", 1)[0].strip().lower() or None


def _extract_text(docling_document: Any) -> str:
    for method_name in ("export_to_markdown", "export_to_text"):
        method = getattr(docling_document, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, str) and value.strip():
                return value
    value = getattr(docling_document, "text", None)
    if isinstance(value, str):
        return value
    return ""


def _extract_segments(docling_document: Any) -> tuple[ParsedDoclingSegment, ...]:
    iterator = getattr(docling_document, "iterate_items", None)
    if callable(iterator):
        segments = _segments_from_items(iterator())
        if segments:
            return segments

    for attr_name in ("segments", "items", "texts", "chunks"):
        items = getattr(docling_document, attr_name, None)
        if items is None:
            continue
        segments = _segments_from_items(items)
        if segments:
            return segments

    return ()


def _segments_from_items(items: Iterable[Any]) -> tuple[ParsedDoclingSegment, ...]:
    segments: list[ParsedDoclingSegment] = []
    for raw_item in items:
        item, extra_metadata = _unwrap_item(raw_item)
        text = _item_text(item)
        if not text:
            continue
        segment = ParsedDoclingSegment(
            index=len(segments),
            text=text,
            page=_item_page(item),
            heading=_item_heading(item, text),
            section=_item_section(item, text),
            metadata=_item_metadata(item, extra_metadata),
        )
        segments.append(segment)
    return tuple(segments)


def _unwrap_item(raw_item: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(raw_item, tuple) and raw_item:
        metadata: dict[str, Any] = {}
        if len(raw_item) > 1:
            metadata["docling_tuple_metadata"] = [
                _json_safe(value) for value in raw_item[1:]
            ]
        return raw_item[0], metadata
    return raw_item, {}


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    for attr_name in ("text", "content", "orig"):
        value = getattr(item, attr_name, None)
        if isinstance(value, str) and value.strip():
            return value
    for method_name in ("export_to_markdown", "export_to_text"):
        method = getattr(item, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _item_page(item: Any) -> int | None:
    for attr_name in ("page", "page_no", "page_number"):
        value = getattr(item, attr_name, None)
        parsed = _as_int(value)
        if parsed is not None:
            return parsed

    provenance = getattr(item, "prov", None)
    if isinstance(provenance, Iterable) and not isinstance(provenance, str):
        for entry in provenance:
            for attr_name in ("page_no", "page", "page_number"):
                parsed = _as_int(getattr(entry, attr_name, None))
                if parsed is not None:
                    return parsed
    return None


def _item_heading(item: Any, text: str) -> str | None:
    explicit = _metadata_or_attr(item, "heading")
    if explicit is not None:
        return explicit
    if _is_heading_item(item):
        return text
    return None


def _item_section(item: Any, text: str) -> str | None:
    for key in ("section", "section_title"):
        value = _metadata_or_attr(item, key)
        if value is not None:
            return value
    if _is_heading_item(item):
        return text
    return None


def _is_heading_item(item: Any) -> bool:
    class_name = type(item).__name__.lower()
    if _has_heading_marker(class_name):
        return True
    label = _metadata_or_attr(item, "label")
    return label is not None and _has_heading_marker(label.lower())


def _has_heading_marker(value: str) -> bool:
    return "heading" in value or "header" in value or "title" in value


def _item_metadata(item: Any, extra_metadata: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    raw_metadata = getattr(item, "metadata", None)
    if isinstance(raw_metadata, Mapping):
        metadata.update({str(key): _json_safe(value) for key, value in raw_metadata.items()})
    for attr_name in ("label", "kind", "level"):
        value = getattr(item, attr_name, None)
        if value is not None and _is_json_scalar(value):
            metadata[attr_name] = value
    metadata.update({str(key): _json_safe(value) for key, value in extra_metadata.items()})
    return metadata


def _metadata_or_attr(item: Any, key: str) -> str | None:
    value = getattr(item, key, None)
    if isinstance(value, str) and value.strip():
        return value
    metadata = getattr(item, "metadata", None)
    if isinstance(metadata, Mapping):
        metadata_value = metadata.get(key)
        if isinstance(metadata_value, str) and metadata_value.strip():
            return metadata_value
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _write_parsed_representation(
    parsed_representation_path: Path,
    parsed: ParsedDoclingDocument,
) -> None:
    parsed_representation_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = parsed_representation_path.with_name(
        f".{parsed_representation_path.name}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(parsed.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(parsed_representation_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _failure(
    document: Document,
    *,
    error_type: str,
    reason: str,
    details: str | None = None,
) -> DoclingParserFailure:
    return DoclingParserFailure(
        document_id=document.id,
        parser="docling",
        raw_asset_path=document.raw_asset_path,
        parsed_representation_path=document.parsed_representation_path,
        error_type=error_type,
        reason=reason,
        details=details or reason,
    )


def _converter_name(converter: DoclingConverter) -> str:
    converter_type = type(converter)
    return f"{converter_type.__module__}.{converter_type.__qualname__}"


def _json_safe(value: Any) -> Any:
    if _is_json_scalar(value):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return str(value)


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


__all__ = [
    "DoclingConverter",
    "DoclingParserFailure",
    "ParsedDoclingDocument",
    "ParsedDoclingSegment",
    "parse_docling_document",
]
