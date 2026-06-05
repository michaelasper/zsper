"""Deterministic RAG parser selection."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

from zsper.profiles import Profile
from zsper.rag.models import DOCUMENT_PARSERS, DOCUMENT_SOURCE_TYPES
from zsper.rag.policy import RagPolicyError, RagPolicyGate
from zsper.security.network_policy import check_network_policy, looks_like_url


TEXT_EXTENSIONS = frozenset(
    {
        ".bash",
        ".c",
        ".cc",
        ".cfg",
        ".conf",
        ".cpp",
        ".cs",
        ".css",
        ".csv",
        ".cxx",
        ".env",
        ".fish",
        ".go",
        ".h",
        ".hpp",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".kt",
        ".kts",
        ".log",
        ".lua",
        ".m",
        ".markdown",
        ".md",
        ".mdx",
        ".php",
        ".pl",
        ".ps1",
        ".py",
        ".r",
        ".rb",
        ".rs",
        ".rst",
        ".scala",
        ".sh",
        ".sql",
        ".swift",
        ".text",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
        ".zsh",
    }
)
TEXT_FILENAMES = frozenset(
    {
        ".env",
        "dockerfile",
        "gemfile",
        "justfile",
        "makefile",
        "procfile",
        "rakefile",
    }
)
DOCLING_EXTENSIONS = frozenset(
    {
        ".doc",
        ".docx",
        ".htm",
        ".html",
        ".odp",
        ".ods",
        ".odt",
        ".pdf",
        ".ppt",
        ".pptx",
        ".rtf",
        ".xls",
        ".xlsx",
    }
)
TEXT_MEDIA_TYPES = frozenset(
    {
        "application/json",
        "application/toml",
        "application/x-yaml",
        "application/yaml",
        "text/csv",
        "text/markdown",
        "text/plain",
        "text/x-markdown",
        "text/x-python",
        "text/x-rst",
        "text/x-yaml",
    }
)
DOCLING_MEDIA_TYPES = frozenset(
    {
        "application/msword",
        "application/pdf",
        "application/rtf",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.oasis.opendocument.presentation",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/html",
    }
)
SUPPORTED_SOURCE_TYPES = frozenset({"file", "repo", "url"})
SUPPORTED_INPUT_SUMMARY = (
    "Markdown, text, JSON, YAML, source, PDF, Office, HTML, URL, or repo"
)


class ParserSelectionError(ValueError):
    """Raised when no actionable parser route exists for an input."""


@dataclass(frozen=True)
class ParserRoute:
    """Parser adapter route selected for a RAG source."""

    parser: str
    source_type: str
    source: str
    media_type: str | None
    extension: str | None
    reason: str

    def __post_init__(self) -> None:
        if self.parser not in DOCUMENT_PARSERS:
            raise ParserSelectionError(f"invalid parser route: {self.parser}")
        if self.source_type not in DOCUMENT_SOURCE_TYPES:
            raise ParserSelectionError(f"invalid parser source_type: {self.source_type}")
        if not self.source:
            raise ParserSelectionError("parser route source must be non-empty")
        if not self.reason:
            raise ParserSelectionError("parser route reason must be non-empty")


def select_parser(
    source: str | Path,
    *,
    profile: Profile,
    source_type: str | None = None,
    media_type: str | None = None,
    user_triggered: bool = False,
    gate: RagPolicyGate | None = None,
) -> ParserRoute:
    """Select a parser route without invoking parser adapters."""

    resolved_source_type = _resolve_source_type(source, source_type)
    normalized_media_type = _normalize_media_type(media_type) or _guess_media_type(source)
    extension = _extension_for(source, resolved_source_type)
    policy_gate = gate or RagPolicyGate(profile)

    if resolved_source_type == "url":
        reason = _require_url_ingest(
            profile,
            policy_gate,
            source,
            user_triggered=user_triggered,
        )
        return ParserRoute(
            parser="web-capture",
            source_type="url",
            source=str(source),
            media_type=normalized_media_type,
            extension=extension,
            reason=reason,
        )

    if resolved_source_type == "repo":
        _require_local_ingest(policy_gate, source)
        return ParserRoute(
            parser="repo",
            source_type="repo",
            source=str(source),
            media_type=normalized_media_type,
            extension=extension,
            reason="repo source routed to repo parser",
        )

    _require_local_ingest(policy_gate, source)
    parser, reason = _select_file_parser(
        source=source,
        media_type=normalized_media_type,
        extension=extension,
    )
    return ParserRoute(
        parser=parser,
        source_type="file",
        source=str(source),
        media_type=normalized_media_type,
        extension=extension,
        reason=reason,
    )


def _resolve_source_type(source: str | Path, source_type: str | None) -> str:
    if source_type is None:
        if looks_like_url(source):
            return "url"
        source_path = Path(source).expanduser()
        if source_path.exists() and source_path.is_dir():
            return "repo"
        return "file"
    if source_type not in SUPPORTED_SOURCE_TYPES:
        allowed = ", ".join(sorted(SUPPORTED_SOURCE_TYPES))
        raise ParserSelectionError(
            f"unsupported parser source_type: {source_type}; expected one of: {allowed}"
        )
    if source_type == "url" and not looks_like_url(source):
        raise ParserSelectionError("url parser source_type requires an http(s) URL")
    if source_type in {"file", "repo"} and looks_like_url(source):
        raise ParserSelectionError(
            f"{source_type} parser source_type requires a local path, not a URL"
        )
    return source_type


def _select_file_parser(
    *,
    source: str | Path,
    media_type: str | None,
    extension: str | None,
) -> tuple[str, str]:
    filename = Path(str(source)).name.lower()
    if _is_docling_media_type(media_type):
        return "docling", f"{media_type} routes to Docling"
    if extension in DOCLING_EXTENSIONS:
        return "docling", f"{extension} routes to Docling"
    if _is_text_media_type(media_type):
        return "text", f"{media_type} routes to local text parser"
    if extension in TEXT_EXTENSIONS:
        return "text", f"{extension} routes to local text parser"
    if filename in TEXT_FILENAMES:
        return "text", f"{filename} routes to local text parser"

    raise ParserSelectionError(
        "unsupported parser input "
        f"source={str(source)!r}, media_type={media_type or 'unknown'}, "
        f"extension={extension or 'none'}; expected {SUPPORTED_INPUT_SUMMARY}"
    )


def _require_url_ingest(
    profile: Profile,
    gate: RagPolicyGate,
    source: str | Path,
    *,
    user_triggered: bool,
) -> str:
    gate.require_ingest(source, user_triggered=user_triggered)
    decision = check_network_policy(
        profile.network_policy,
        source,
        action="url-ingest",
        user_triggered=user_triggered,
    )
    if not decision.allowed:
        raise RagPolicyError(decision.reason)
    return decision.reason


def _require_local_ingest(gate: RagPolicyGate, source: str | Path) -> None:
    gate.require_ingest(source, user_triggered=False)


def _normalize_media_type(media_type: str | None) -> str | None:
    if media_type is None:
        return None
    return media_type.split(";", 1)[0].strip().lower() or None


def _guess_media_type(source: str | Path) -> str | None:
    guessed = mimetypes.guess_type(str(source))[0]
    return _normalize_media_type(guessed)


def _extension_for(source: str | Path, source_type: str) -> str | None:
    if source_type == "url":
        return None
    suffix = Path(str(source)).suffix.lower()
    return suffix or None


def _is_text_media_type(media_type: str | None) -> bool:
    if media_type is None:
        return False
    if media_type in TEXT_MEDIA_TYPES:
        return True
    return media_type.startswith("text/") and media_type != "text/html"


def _is_docling_media_type(media_type: str | None) -> bool:
    return media_type in DOCLING_MEDIA_TYPES if media_type is not None else False
