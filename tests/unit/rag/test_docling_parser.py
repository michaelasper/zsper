import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zsper.profiles import initialize_profile
from zsper.rag.assets import capture_local_asset
from zsper.rag.models import Document
from zsper.rag.parsers.docling import (
    DoclingParserFailure,
    ParsedDoclingDocument,
    parse_docling_document,
)
from zsper.rag.store import ProfileRagStore


@dataclass(frozen=True)
class _FakeDoclingItem:
    text: str
    page: int | None = None
    heading: str | None = None
    section: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class _FakeDoclingLabeledItem:
    text: str
    page: int | None = None
    label: str | None = None
    level: int | None = None
    metadata: dict[str, Any] | None = None


class _FakeDoclingDocument:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    def export_to_markdown(self) -> str:
        return "\n\n".join(item.text for item in self.items)


class _FakeConversionResult:
    def __init__(self, document: _FakeDoclingDocument) -> None:
        self.document = document


class _FakeDoclingConverter:
    def __init__(self, result: _FakeConversionResult) -> None:
        self.result = result
        self.sources: list[str] = []

    def convert(self, source: str) -> _FakeConversionResult:
        self.sources.append(source)
        return self.result


class _FailingDoclingConverter:
    def convert(self, source: str) -> _FakeConversionResult:
        raise RuntimeError(f"cannot parse {source}")


def test_docling_parser_writes_normalized_pdf_representation(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    source = tmp_path / "runbook.pdf"
    source.write_bytes(b"%PDF-1.7\n% fake unit fixture\n")
    document = capture_local_asset(profile, store, source, title="Runbook")
    fake_docling = _FakeDoclingDocument(
        [
            _FakeDoclingItem(
                text="# Incident Runbook",
                page=1,
                heading="Incident Runbook",
                section="Overview",
                metadata={"kind": "heading"},
            ),
            _FakeDoclingItem(
                text="Restart the local worker.",
                page=2,
                heading="Incident Runbook",
                section="Recovery",
                metadata={"kind": "paragraph"},
            ),
        ]
    )
    converter = _FakeDoclingConverter(_FakeConversionResult(fake_docling))

    parsed = parse_docling_document(document, converter=converter)

    assert isinstance(parsed, ParsedDoclingDocument)
    parsed_path = Path(document.parsed_representation_path)
    assert parsed_path.is_file()
    assert parsed_path.parent == Path(profile.root) / "brain" / "parsed"
    assert converter.sources == [document.raw_asset_path]
    assert parsed.document_id == document.id
    assert parsed.parser == "docling"
    assert parsed.text == "# Incident Runbook\n\nRestart the local worker."
    assert parsed.segments[0].page == 1
    assert parsed.segments[0].heading == "Incident Runbook"
    assert parsed.segments[0].section == "Overview"
    assert parsed.segments[0].metadata == {"kind": "heading"}

    representation = json.loads(parsed_path.read_text(encoding="utf-8"))
    assert representation["schema"] == "zsper.rag.docling_parsed.v1"
    assert representation["document_id"] == document.id
    assert representation["parser"] == "docling"
    assert representation["text"] == parsed.text
    assert representation["segments"][1] == {
        "index": 1,
        "text": "Restart the local worker.",
        "page": 2,
        "heading": "Incident Runbook",
        "section": "Recovery",
        "metadata": {"kind": "paragraph"},
    }


def test_docling_parser_preserves_section_header_label_as_heading_and_section(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    source = tmp_path / "runbook.pdf"
    source.write_bytes(b"%PDF-1.7\n% fake unit fixture\n")
    document = capture_local_asset(profile, store, source, title="Runbook")
    fake_docling = _FakeDoclingDocument(
        [
            _FakeDoclingLabeledItem(
                text="Incident Response",
                page=4,
                label="section_header",
                level=2,
                metadata={"level": 2},
            ),
        ]
    )
    converter = _FakeDoclingConverter(_FakeConversionResult(fake_docling))

    parsed = parse_docling_document(document, converter=converter)

    assert isinstance(parsed, ParsedDoclingDocument)
    segment = parsed.segments[0]
    assert segment.page == 4
    assert segment.heading == "Incident Response"
    assert segment.section == "Incident Response"
    assert segment.metadata == {"label": "section_header", "level": 2}

    representation = json.loads(
        Path(document.parsed_representation_path).read_text(encoding="utf-8")
    )
    assert representation["segments"][0] == {
        "index": 0,
        "text": "Incident Response",
        "page": 4,
        "heading": "Incident Response",
        "section": "Incident Response",
        "metadata": {"label": "section_header", "level": 2},
    }


def test_docling_parser_failure_record_does_not_create_chunks_or_parsed_file(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    source = tmp_path / "corrupt.pdf"
    source.write_bytes(b"not a real pdf")
    document = capture_local_asset(profile, store, source, title="Corrupt PDF")

    parsed = parse_docling_document(document, converter=_FailingDoclingConverter())

    assert isinstance(parsed, DoclingParserFailure)
    assert parsed.document_id == document.id
    assert parsed.parser == "docling"
    assert parsed.error_type == "RuntimeError"
    assert "Docling failed to parse document" in parsed.reason
    assert "cannot parse" in parsed.details
    assert not Path(document.parsed_representation_path).exists()
    assert store.list_chunks(profile, document.id) == []


def test_docling_parser_returns_failure_record_for_unsupported_file(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "archive.zip"
    parsed_path = tmp_path / "parsed" / "doc-zip.txt"
    raw_path.write_bytes(b"PK")

    unsupported = Document(
        id="doc-zip",
        profile_id="work",
        source_type="file",
        raw_asset_path=str(raw_path),
        parsed_representation_path=str(parsed_path),
        title="Archive",
        metadata={"media_type": "application/zip"},
        content_hash="sha256:test",
        parser="docling",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )

    parsed = parse_docling_document(unsupported, converter=_FailingDoclingConverter())

    assert isinstance(parsed, DoclingParserFailure)
    assert parsed.error_type == "UnsupportedDoclingSource"
    assert "unsupported Docling parser input" in parsed.reason
    assert not parsed_path.exists()
