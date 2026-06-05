import hashlib
import json
from pathlib import Path

import pytest

from zsper.profiles import Profile, default_profile, initialize_profile
from zsper.rag.models import Document, DocumentChunk
from zsper.rag.policy import RagPolicyError
from zsper.rag.store import ProfileRagStore


def _document(profile: Profile, document_id: str = "doc-1") -> Document:
    return Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=f"{profile.root}/brain/assets/{document_id}.md",
        parsed_representation_path=f"{profile.root}/brain/parsed/{document_id}.txt",
        title="Embedding Fixture",
        metadata={"source_name": f"{document_id}.md"},
        content_hash=f"sha256:{profile.name}-{document_id}",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(
    document_id: str,
    chunk_id: str,
    index: int,
    text: str,
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=index,
        text=text,
        citation_anchor_id=f"anchor-{index}",
        token_estimate=max(1, len(text.split())),
        byte_start=index * 100,
        byte_end=index * 100 + len(text.encode("utf-8")),
        embedding_model=None,
        embedding_vector_id=None,
    )


def _expected_vector_id(
    profile: Profile,
    document_id: str,
    chunk: DocumentChunk,
    model: str,
) -> str:
    payload = {
        "chunk_id": chunk.id,
        "chunk_index": chunk.chunk_index,
        "document_id": document_id,
        "model": model,
        "profile": profile.name,
        "schema": "zsper.rag.embedding_vector_id.v1",
        "text_sha256": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"embvec-{digest}"


def test_embed_chunks_updates_chunks_with_profile_embedding_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.embeddings import DeterministicFakeEmbeddingProvider
    from zsper.rag.embeddings import embed_chunks

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    document = _document(profile)
    first_chunk = _chunk(
        document.id,
        "chunk-1",
        0,
        "Local embeddings should preserve the original chunk text.",
    )
    second_chunk = _chunk(
        document.id,
        "chunk-2",
        1,
        "Dense retrieval metadata is attached after chunking.",
    )
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, first_chunk)
    store.upsert_chunk(profile, second_chunk)
    provider = DeterministicFakeEmbeddingProvider(model=profile.embedding_profile)

    result = embed_chunks(profile, store, document.id, provider=provider)

    expected_ids = tuple(
        _expected_vector_id(profile, document.id, chunk, profile.embedding_profile)
        for chunk in (first_chunk, second_chunk)
    )
    assert result.document_id == document.id
    assert result.embedding_model == profile.embedding_profile
    assert result.chunk_count == 2
    assert result.vector_ids == expected_ids
    assert result.vectors == (
        (0.0, float(len(first_chunk.text)), float(sum(first_chunk.text.encode("utf-8")) % 997)),
        (1.0, float(len(second_chunk.text)), float(sum(second_chunk.text.encode("utf-8")) % 997)),
    )

    updated_chunks = store.list_chunks(profile, document.id)
    assert updated_chunks == [
        DocumentChunk(
            **{
                **first_chunk.to_dict(),
                "embedding_model": profile.embedding_profile,
                "embedding_vector_id": expected_ids[0],
            }
        ),
        DocumentChunk(
            **{
                **second_chunk.to_dict(),
                "embedding_model": profile.embedding_profile,
                "embedding_vector_id": expected_ids[1],
            }
        ),
    ]


def test_vector_ids_are_stable_and_content_based(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.embeddings import DeterministicFakeEmbeddingProvider
    from zsper.rag.embeddings import embed_chunks

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    document = _document(profile, "doc-stable")
    chunk = _chunk(document.id, "chunk-stable", 0, "Original content.")
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)
    provider = DeterministicFakeEmbeddingProvider(model=profile.embedding_profile)

    first = embed_chunks(profile, store, document.id, provider=provider)
    second = embed_chunks(profile, store, document.id, provider=provider)

    changed_chunk = DocumentChunk(
        **{
            **chunk.to_dict(),
            "text": "Changed content.",
            "embedding_model": None,
            "embedding_vector_id": None,
        }
    )
    store.upsert_chunk(profile, changed_chunk)
    changed = embed_chunks(profile, store, document.id, provider=provider)

    assert first.vector_ids == second.vector_ids
    assert changed.vector_ids != first.vector_ids


def test_air_offline_default_provider_uses_local_small_embedding_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.embeddings import embed_chunks

    calls: list[tuple[object, ...]] = []

    def forbidden_network_call(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise AssertionError("local embedding worker must not use network")

    monkeypatch.setattr("socket.create_connection", forbidden_network_call)
    monkeypatch.setattr("urllib.request.urlopen", forbidden_network_call)
    profile = initialize_profile(
        mode="air-offline",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    document = _document(profile)
    chunk = _chunk(document.id, "chunk-air", 0, "Air mode embeds local files.")
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)

    result = embed_chunks(profile, store, document.id)

    assert result.embedding_model == "local-small-embedding"
    assert result.chunk_count == 1
    assert store.list_chunks(profile, document.id)[0].embedding_model == (
        "local-small-embedding"
    )
    assert calls == []


def test_hosted_embedding_settings_fail_policy_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from zsper.rag.embeddings import provider_for_profile

    calls: list[tuple[object, ...]] = []

    def forbidden_urlopen(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise AssertionError("policy must reject hosted embeddings before HTTP")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_urlopen)
    profile = default_profile(mode="work", root=tmp_path / "work")

    with pytest.raises(RagPolicyError, match="forbidden hosted RAG settings"):
        provider_for_profile(
            profile,
            settings={
                "provider": "openai",
                "base_url": "https://api.openai.com/v1/embeddings",
            },
        )

    assert calls == []
