"""Local text parser for already-captured text-like RAG assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zsper.rag.models import Document


class TextParserError(ValueError):
    """Raised when a document cannot be parsed by the local text parser."""


@dataclass(frozen=True)
class ParsedText:
    document_id: str
    parser: str
    text: str
    raw_asset_path: str
    parsed_representation_path: str
    encoding: str
    byte_length: int


def parse_text_document(document: Document, *, encoding: str = "utf-8") -> ParsedText:
    """Decode a text-routed document and write its parsed representation."""

    if document.parser != "text":
        raise TextParserError(
            "text parser only accepts text routes; "
            f"document {document.id} is routed to {document.parser}"
        )

    raw_asset_path = Path(document.raw_asset_path)
    parsed_representation_path = Path(document.parsed_representation_path)
    try:
        raw_bytes = raw_asset_path.read_bytes()
    except OSError as exc:
        raise TextParserError(
            f"text parser could not read raw asset for document {document.id}: "
            f"{raw_asset_path}"
        ) from exc

    try:
        text = raw_bytes.decode(encoding)
    except UnicodeDecodeError as exc:
        raise TextParserError(
            f"text parser could not decode document {document.id} as {encoding}; "
            "route binary or complex documents to Docling"
        ) from exc

    parsed_representation_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_representation_path.write_text(text, encoding=encoding)
    return ParsedText(
        document_id=document.id,
        parser="text",
        text=text,
        raw_asset_path=str(raw_asset_path),
        parsed_representation_path=str(parsed_representation_path),
        encoding=encoding,
        byte_length=len(raw_bytes),
    )
