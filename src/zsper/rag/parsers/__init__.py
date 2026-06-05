"""RAG parser selection and local parser adapters."""

from zsper.rag.parsers.selector import (
    DOCLING_EXTENSIONS,
    SUPPORTED_INPUT_SUMMARY,
    TEXT_EXTENSIONS,
    ParserRoute,
    ParserSelectionError,
    select_parser,
)
from zsper.rag.parsers.text import ParsedText, TextParserError, parse_text_document

__all__ = [
    "DOCLING_EXTENSIONS",
    "SUPPORTED_INPUT_SUMMARY",
    "TEXT_EXTENSIONS",
    "ParsedText",
    "ParserRoute",
    "ParserSelectionError",
    "TextParserError",
    "parse_text_document",
    "select_parser",
]
