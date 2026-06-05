from pathlib import Path

import pytest

from zsper.profiles import default_profile
from zsper.rag.models import Document
from zsper.rag.parsers import (
    ParserSelectionError,
    TextParserError,
    parse_text_document,
    select_parser,
)
from zsper.rag.policy import RagPolicyError


def _profile(mode: str, tmp_path: Path):
    return default_profile(mode=mode, root=tmp_path / mode)


@pytest.mark.parametrize(
    ("source", "media_type", "expected_parser"),
    [
        ("README.md", None, "text"),
        ("notes.markdown", None, "text"),
        ("plain.txt", "text/plain", "text"),
        ("payload.json", "application/json", "text"),
        ("config.yaml", None, "text"),
        ("config.yml", "application/x-yaml", "text"),
        ("worker.py", "text/x-python", "text"),
        ("component.tsx", None, "text"),
        ("query.sql", None, "text"),
        ("Dockerfile", "text/plain", "text"),
        ("manual.pdf", "application/pdf", "docling"),
        ("report.docx", None, "docling"),
        ("slides.pptx", None, "docling"),
        ("sheet.xlsx", None, "docling"),
        ("complex.html", "text/html", "docling"),
    ],
)
def test_file_parser_selection_matrix_covers_supported_extensions(
    tmp_path: Path,
    source: str,
    media_type: str | None,
    expected_parser: str,
) -> None:
    route = select_parser(
        tmp_path / source,
        profile=_profile("work", tmp_path),
        media_type=media_type,
    )

    assert route.parser == expected_parser
    assert route.source_type == "file"
    if media_type is not None:
        assert route.media_type == media_type


@pytest.mark.parametrize(
    ("source", "media_type", "expected_parser"),
    [
        ("download", "application/pdf", "docling"),
        ("payload", "application/json", "text"),
        ("script", "text/x-python", "text"),
        ("page", "text/html", "docling"),
    ],
)
def test_parser_selection_uses_mime_type_without_extension(
    tmp_path: Path,
    source: str,
    media_type: str,
    expected_parser: str,
) -> None:
    route = select_parser(
        tmp_path / source,
        profile=_profile("work", tmp_path),
        media_type=media_type,
    )

    assert route.parser == expected_parser
    assert route.reason


def test_allowed_url_routes_to_web_capture(tmp_path: Path) -> None:
    route = select_parser(
        "https://example.com/research",
        profile=_profile("work", tmp_path),
        user_triggered=True,
    )

    assert route.parser == "web-capture"
    assert route.source_type == "url"
    assert route.reason == "local-first policy allows explicit web capture"


def test_air_offline_url_rejected_by_policy_before_web_capture(tmp_path: Path) -> None:
    with pytest.raises(RagPolicyError, match="offline policy blocks url-ingest"):
        select_parser(
            "https://example.com/research",
            profile=_profile("air-offline", tmp_path),
            user_triggered=True,
        )


def test_repo_docs_route_to_repo_parser(tmp_path: Path) -> None:
    route = select_parser(
        tmp_path / "repo" / "docs",
        profile=_profile("work", tmp_path),
        source_type="repo",
    )

    assert route.parser == "repo"
    assert route.source_type == "repo"
    assert "repo" in route.reason


def test_unsupported_input_returns_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ParserSelectionError) as exc_info:
        select_parser(
            tmp_path / "archive.zip",
            profile=_profile("work", tmp_path),
        )

    message = str(exc_info.value)
    assert "unsupported parser input" in message
    assert ".zip" in message
    assert "Markdown, text, JSON, YAML, source, PDF, Office, HTML, URL, or repo" in message


def test_selected_parser_can_be_recorded_on_document(tmp_path: Path) -> None:
    profile = _profile("work", tmp_path)
    route = select_parser(tmp_path / "notes.md", profile=profile)

    document = Document(
        id="doc-1",
        profile_id=profile.name,
        source_type=route.source_type,
        raw_asset_path=str(tmp_path / "notes.md"),
        parsed_representation_path=str(tmp_path / "parsed" / "doc-1.txt"),
        title="Notes",
        metadata={"parser_reason": route.reason},
        content_hash="sha256:test",
        parser=route.parser,
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )

    assert document.parser == "text"


def test_text_parser_writes_local_text_representation(tmp_path: Path) -> None:
    raw_path = tmp_path / "source.py"
    parsed_path = tmp_path / "parsed" / "doc-1.txt"
    raw_path.write_text("def main() -> str:\n    return 'local'\n", encoding="utf-8")
    document = Document(
        id="doc-1",
        profile_id="work",
        source_type="file",
        raw_asset_path=str(raw_path),
        parsed_representation_path=str(parsed_path),
        title="Source",
        metadata={},
        content_hash="sha256:test",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )

    parsed = parse_text_document(document)

    assert parsed.parser == "text"
    assert parsed.document_id == document.id
    assert parsed.text == raw_path.read_text(encoding="utf-8")
    assert parsed.byte_length == raw_path.stat().st_size
    assert parsed_path.read_text(encoding="utf-8") == parsed.text


def test_text_parser_rejects_non_text_document_actionably(tmp_path: Path) -> None:
    document = Document(
        id="doc-1",
        profile_id="work",
        source_type="file",
        raw_asset_path=str(tmp_path / "source.pdf"),
        parsed_representation_path=str(tmp_path / "parsed" / "doc-1.txt"),
        title="PDF",
        metadata={},
        content_hash="sha256:test",
        parser="docling",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )

    with pytest.raises(TextParserError, match="text parser only accepts text routes"):
        parse_text_document(document)
