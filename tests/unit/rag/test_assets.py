import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from zsper.profiles import initialize_profile
from zsper.rag.assets import RawAssetCaptureError, capture_local_asset
from zsper.rag.store import ProfileRagStore


def _content_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_capture_local_files_copies_markdown_pdf_and_source_to_profile_assets(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    source_root = tmp_path / "sources"
    source_root.mkdir()
    markdown = source_root / "design-notes.md"
    pdf = source_root / "runbook.pdf"
    code_dir = source_root / "src"
    code_dir.mkdir()
    source_file = code_dir / "adapter.py"
    markdown.write_text("# Design Notes\n\nCapture this markdown.\n", encoding="utf-8")
    pdf.write_bytes(b"%PDF-1.7\n% raw pdf fixture bytes\n")
    source_file.write_text("def adapter() -> str:\n    return 'local'\n", encoding="utf-8")

    documents = [
        capture_local_asset(profile, store, markdown, title="Design Notes"),
        capture_local_asset(profile, store, pdf, title="Runbook PDF"),
        capture_local_asset(profile, store, source_file, title="Adapter Source"),
    ]

    assets_dir = Path(profile.root) / "brain" / "assets"
    parsed_dir = Path(profile.root) / "brain" / "parsed"
    for document, source, title in zip(
        documents,
        (markdown, pdf, source_file),
        ("Design Notes", "Runbook PDF", "Adapter Source"),
        strict=True,
    ):
        raw_asset_path = Path(document.raw_asset_path)
        parsed_path = Path(document.parsed_representation_path)

        assert raw_asset_path.is_file()
        assert raw_asset_path.is_relative_to(assets_dir)
        assert raw_asset_path.read_bytes() == source.read_bytes()
        assert parsed_path.parent == parsed_dir
        assert not parsed_path.exists()
        assert document.profile_id == profile.name
        assert document.source_type == "file"
        assert document.title == title
        assert document.content_hash == _content_hash(source)
        assert document.metadata["source_type"] == "file"
        assert document.metadata["title"] == title
        assert document.metadata["original_path"] == str(source.resolve())
        assert document.metadata["original_url"] is None
        assert document.metadata["captured_at"] == document.created_at
        datetime.fromisoformat(document.metadata["captured_at"])

    assert {Path(document.raw_asset_path).suffix for document in documents} == {
        ".md",
        ".pdf",
        ".py",
    }
    assert {document.parser for document in documents} == {"text", "docling"}
    assert {document.id for document in store.list_documents(profile)} == {
        document.id for document in documents
    }


def test_reingesting_unchanged_local_file_returns_existing_document_version(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    source = tmp_path / "notes.md"
    source.write_text("same bytes should not create a new version\n", encoding="utf-8")

    first = capture_local_asset(profile, store, source, title="Stable Notes")
    second = capture_local_asset(profile, store, source, title="Stable Notes")

    assert second == first
    assert store.list_documents(profile) == [first]
    assert list((Path(profile.root) / "brain" / "assets").iterdir()) == [
        Path(first.raw_asset_path)
    ]
    assert first.metadata["version"] == 1

    ledger_rows = [
        json.loads(line)
        for line in (
            Path(profile.root) / "brain" / "ledgers" / "documents.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["record_id"] for row in ledger_rows] == [first.id]


def test_capture_rejects_path_traversal_attempts(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    source_root = tmp_path / "sources"
    source_root.mkdir()
    outside_source = tmp_path / "outside.md"
    outside_source.write_text("do not capture through traversal\n", encoding="utf-8")

    with pytest.raises(RawAssetCaptureError, match="path traversal"):
        capture_local_asset(profile, store, source_root / ".." / "outside.md")

    assert list((Path(profile.root) / "brain" / "assets").iterdir()) == []
    assert store.list_documents(profile) == []
