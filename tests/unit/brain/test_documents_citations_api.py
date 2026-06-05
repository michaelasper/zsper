from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from zsper.profiles import Profile, initialize_profile
from zsper.rag import CitationAnchor, Document, DocumentChunk, ProfileRagStore


SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services" / "brain-api"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402


def _service_env(profile: Profile, registry_path: Path, rag_db_path: Path) -> dict[str, str]:
    return {
        "ZSPER_PROFILE_ID": profile.name,
        "ZSPER_PROFILE_ROOT": profile.root,
        "ZSPER_PROFILE_REGISTRY": str(registry_path),
        "ZSPER_RAG_SQLITE_PATH": str(rag_db_path),
        "POSTGRES_DB": profile.database_name,
        "POSTGRES_DSN": f"postgresql://zsper:local@127.0.0.1/{profile.database_name}",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_KEY_PREFIX": f"zsper:{profile.name}:",
        "ZSPER_MODEL_BASE_URL": "http://127.0.0.1:9127/v1",
    }


def _document(
    profile: Profile,
    parsed_path: Path,
    *,
    document_id: str,
    title: str,
    metadata: dict[str, Any] | None = None,
) -> Document:
    return Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(parsed_path.with_suffix(".raw")),
        parsed_representation_path=str(parsed_path),
        title=title,
        metadata={
            "source_name": parsed_path.name,
            "api_key": "fixture-secret-key",
            **(metadata or {}),
        },
        content_hash=f"sha256:{profile.name}:{document_id}",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(
    *,
    document_id: str,
    chunk_id: str = "chunk-target",
    anchor_id: str = "anchor-target",
    text: str = "TARGET-CHUNK",
    byte_start: int | None = 10,
    byte_end: int | None = 22,
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=0,
        text=text,
        citation_anchor_id=anchor_id,
        token_estimate=3,
        byte_start=byte_start,
        byte_end=byte_end,
        embedding_model=None,
        embedding_vector_id=None,
    )


def _anchor(
    *,
    document_id: str,
    chunk_id: str = "chunk-target",
    anchor_id: str = "anchor-target",
    source_path_or_url: str = "/fixtures/source.txt",
) -> CitationAnchor:
    return CitationAnchor(
        id=anchor_id,
        document_id=document_id,
        chunk_id=chunk_id,
        label="Fixture chunk",
        source_path_or_url=source_path_or_url,
        display_range="bytes 10-22",
    )


def test_documents_api_lists_only_active_profile_documents_with_audit_ids_and_redaction(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    personal = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    rag_db_path = tmp_path / "rag.sqlite"
    store = ProfileRagStore.sqlite(rag_db_path)
    work_parsed_path = Path(work.root) / "brain" / "parsed" / "work.txt"
    personal_parsed_path = Path(personal.root) / "brain" / "parsed" / "personal.txt"
    work_document = _document(
        work,
        work_parsed_path,
        document_id="doc-work",
        title="Work Document",
    )
    personal_document = _document(
        personal,
        personal_parsed_path,
        document_id="doc-personal",
        title="Personal Document",
    )
    store.upsert_document(work, work_document)
    store.upsert_document(personal, personal_document)
    client = TestClient(
        create_app(environ=_service_env(work, isolated_registry_path, rag_db_path))
    )

    response = client.get(
        "/api/documents",
        headers={"X-Zsper-Profile-Id": "work"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "work"
    assert body["document_ids"] == ["doc-work"]
    assert [document["document_id"] for document in body["documents"]] == ["doc-work"]
    assert body["documents"][0]["profile_id"] == "work"
    assert body["documents"][0]["metadata"]["api_key"] == "[REDACTED]"
    assert "fixture-secret-key" not in response.text
    assert "doc-personal" not in response.text


def test_documents_api_gets_and_inspects_document_chunks_and_citations(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    rag_db_path = tmp_path / "rag.sqlite"
    store = ProfileRagStore.sqlite(rag_db_path)
    parsed_path = Path(profile.root) / "brain" / "parsed" / "source.txt"
    document = _document(
        profile,
        parsed_path,
        document_id="doc-work",
        title="Work Document",
    )
    chunk = _chunk(document_id=document.id)
    anchor = _anchor(
        document_id=document.id,
        source_path_or_url=str(parsed_path.with_suffix(".source")),
    )
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)
    store.upsert_citation_anchor(profile, anchor)
    client = TestClient(
        create_app(environ=_service_env(profile, isolated_registry_path, rag_db_path))
    )

    document_response = client.get(
        "/api/documents/doc-work",
        headers={"X-Zsper-Profile-Id": "work"},
    )
    inspect_response = client.get(
        "/api/documents/doc-work/inspect",
        headers={"X-Zsper-Profile-Id": "work"},
    )

    assert document_response.status_code == 200
    document_body = document_response.json()
    assert document_body["profile_id"] == "work"
    assert document_body["document_id"] == "doc-work"
    assert document_body["document"]["document_id"] == "doc-work"

    assert inspect_response.status_code == 200
    inspect_body = inspect_response.json()
    assert inspect_body["profile_id"] == "work"
    assert inspect_body["document_id"] == "doc-work"
    assert inspect_body["chunk_ids"] == ["chunk-target"]
    assert inspect_body["citation_anchor_ids"] == ["anchor-target"]
    assert inspect_body["chunks"][0]["profile_id"] == "work"
    assert inspect_body["chunks"][0]["chunk_id"] == "chunk-target"
    assert inspect_body["chunks"][0]["citation_anchor_id"] == "anchor-target"
    assert inspect_body["citations"][0]["profile_id"] == "work"
    assert inspect_body["citations"][0]["citation_anchor_id"] == "anchor-target"


def test_citations_api_lists_gets_and_inspects_source_context(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    rag_db_path = tmp_path / "rag.sqlite"
    store = ProfileRagStore.sqlite(rag_db_path)
    parsed_path = Path(profile.root) / "brain" / "parsed" / "source.txt"
    parsed_path.write_text("aaaaabbbbbTARGET-CHUNKcccccddddd", encoding="utf-8")
    document = _document(
        profile,
        parsed_path,
        document_id="doc-work",
        title="Work Document",
    )
    chunk = _chunk(document_id=document.id)
    anchor = _anchor(
        document_id=document.id,
        source_path_or_url=str(parsed_path.with_suffix(".source")),
    )
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)
    store.upsert_citation_anchor(profile, anchor)
    client = TestClient(
        create_app(environ=_service_env(profile, isolated_registry_path, rag_db_path))
    )

    list_response = client.get(
        "/api/citations",
        params={"document_id": "doc-work"},
        headers={"X-Zsper-Profile-Id": "work"},
    )
    get_response = client.get(
        "/api/citations/anchor-target",
        headers={"X-Zsper-Profile-Id": "work"},
    )
    inspect_response = client.get(
        "/api/citations/anchor-target/inspect",
        params={"context_chars": 3},
        headers={"X-Zsper-Profile-Id": "work"},
    )

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["profile_id"] == "work"
    assert list_body["document_id"] == "doc-work"
    assert list_body["citation_anchor_ids"] == ["anchor-target"]
    assert list_body["citations"][0]["document_id"] == "doc-work"
    assert list_body["citations"][0]["chunk_id"] == "chunk-target"

    assert get_response.status_code == 200
    get_body = get_response.json()
    assert get_body["profile_id"] == "work"
    assert get_body["document_id"] == "doc-work"
    assert get_body["chunk_id"] == "chunk-target"
    assert get_body["citation_anchor_id"] == "anchor-target"
    assert get_body["citation"]["citation_anchor_id"] == "anchor-target"

    assert inspect_response.status_code == 200
    inspect_body = inspect_response.json()
    assert inspect_body["profile_id"] == "work"
    assert inspect_body["document_id"] == "doc-work"
    assert inspect_body["chunk_id"] == "chunk-target"
    assert inspect_body["citation_anchor_id"] == "anchor-target"
    assert inspect_body["context"]["text"] == "bbbTARGET-CHUNKccc"
    assert inspect_body["context"]["citation_text"] == "TARGET-CHUNK"
    assert inspect_body["context"]["citation_start_byte"] == 10
    assert inspect_body["context"]["citation_end_byte"] == 22


def test_cross_profile_document_and_citation_reads_fail(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    personal = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    rag_db_path = tmp_path / "rag.sqlite"
    store = ProfileRagStore.sqlite(rag_db_path)
    personal_parsed_path = Path(personal.root) / "brain" / "parsed" / "personal.txt"
    personal_document = _document(
        personal,
        personal_parsed_path,
        document_id="doc-personal",
        title="Personal Document",
    )
    personal_chunk = _chunk(
        document_id=personal_document.id,
        chunk_id="chunk-personal",
        anchor_id="anchor-personal",
        text="personal-only",
        byte_start=0,
        byte_end=13,
    )
    personal_anchor = _anchor(
        document_id=personal_document.id,
        chunk_id=personal_chunk.id,
        anchor_id=personal_chunk.citation_anchor_id,
    )
    store.upsert_document(personal, personal_document)
    store.upsert_chunk(personal, personal_chunk)
    store.upsert_citation_anchor(personal, personal_anchor)
    client = TestClient(
        create_app(environ=_service_env(work, isolated_registry_path, rag_db_path))
    )

    document_response = client.get(
        "/api/documents/doc-personal",
        headers={"X-Zsper-Profile-Id": "work"},
    )
    citation_response = client.get(
        "/api/citations/anchor-personal",
        headers={"X-Zsper-Profile-Id": "work"},
    )
    mismatched_header_response = client.get(
        "/api/documents",
        headers={"X-Zsper-Profile-Id": "personal"},
    )

    assert document_response.status_code == 404
    assert document_response.json()["error"]["code"] == "document_not_found"
    assert document_response.json()["error"]["profile_id"] == "work"
    assert citation_response.status_code == 404
    assert citation_response.json()["error"]["code"] == "citation_anchor_not_found"
    assert citation_response.json()["error"]["profile_id"] == "work"
    assert mismatched_header_response.status_code == 403
    assert (
        mismatched_header_response.json()["error"]["code"]
        == "profile_context_mismatch"
    )
