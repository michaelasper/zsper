import builtins
import hashlib
import json
from collections.abc import Sequence
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


def test_default_provider_requires_sentence_transformers_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from zsper.rag.embeddings import EmbeddingError
    from zsper.rag.embeddings import provider_for_profile

    real_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "sentence_transformers" or name.startswith(
            "sentence_transformers."
        ):
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    profile = default_profile(mode="work", root=tmp_path / "work")

    with pytest.raises(EmbeddingError, match="uv sync --group rag"):
        provider_for_profile(profile)


def test_local_embedding_provider_batches_through_worker_contract() -> None:
    from zsper.rag.embeddings import LocalEmbeddingProvider

    class RecordingWorker:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[str, ...]]] = []

        def embed_texts(
            self,
            model: str,
            texts: Sequence[str],
        ) -> tuple[tuple[float, ...], ...]:
            batch = tuple(texts)
            self.calls.append((model, batch))
            return tuple((float(len(text)),) for text in batch)

    worker = RecordingWorker()
    provider = LocalEmbeddingProvider(
        model="local-small-embedding",
        worker=worker,
        batch_size=2,
    )

    vectors = provider.embed_texts(["a", "bb", "ccc", "dddd", "eeeee"])

    assert vectors == ((1.0,), (2.0,), (3.0,), (4.0,), (5.0,))
    assert worker.calls == [
        ("local-small-embedding", ("a", "bb")),
        ("local-small-embedding", ("ccc", "dddd")),
        ("local-small-embedding", ("eeeee",)),
    ]


def test_sentence_transformer_worker_reuses_loaded_model_per_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zsper.rag.embeddings import LocalEmbeddingProvider

    constructed_models: list[tuple[str, dict[str, object]]] = []
    encoded_batches: list[tuple[str, ...]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name_or_path: str, **kwargs: object) -> None:
            constructed_models.append((model_name_or_path, kwargs))

        def encode(
            self,
            texts: Sequence[str],
            **kwargs: object,
        ) -> tuple[tuple[float, ...], ...]:
            encoded_batches.append(tuple(texts))
            return tuple((float(len(text)),) for text in texts)

    monkeypatch.setattr(
        "zsper.rag.embeddings._sentence_transformer_class",
        lambda: FakeSentenceTransformer,
        raising=False,
    )
    provider = LocalEmbeddingProvider(
        model="local-small-embedding",
        batch_size=2,
    )

    assert provider.embed_texts(["a", "bb", "ccc", "dddd"]) == (
        (1.0,),
        (2.0,),
        (3.0,),
        (4.0,),
    )
    assert encoded_batches == [("a", "bb"), ("ccc", "dddd")]
    assert constructed_models == [
        (
            "sentence-transformers/all-MiniLM-L6-v2",
            {"local_files_only": True, "trust_remote_code": False},
        )
    ]


def test_default_provider_reuses_loaded_model_between_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from zsper.rag.embeddings import provider_for_profile

    constructed_models: list[str] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name_or_path: str, **kwargs: object) -> None:
            del kwargs
            constructed_models.append(model_name_or_path)

        def encode(
            self,
            texts: Sequence[str],
            **kwargs: object,
        ) -> tuple[tuple[float, ...], ...]:
            return tuple((float(len(text)),) for text in texts)

    monkeypatch.setattr(
        "zsper.rag.embeddings._sentence_transformer_class",
        lambda: FakeSentenceTransformer,
        raising=False,
    )
    profile = default_profile(mode="air-offline", root=tmp_path / "air")

    provider_for_profile(profile).embed_texts(["first"])
    provider_for_profile(profile).embed_texts(["second"])

    assert constructed_models == ["sentence-transformers/all-MiniLM-L6-v2"]


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

    constructed_models: list[tuple[str, dict[str, object]]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name_or_path: str, **kwargs: object) -> None:
            constructed_models.append((model_name_or_path, kwargs))

        def encode(
            self,
            texts: Sequence[str],
            **kwargs: object,
        ) -> tuple[tuple[float, ...], ...]:
            assert kwargs["show_progress_bar"] is False
            assert kwargs["normalize_embeddings"] is True
            return tuple((float(index), float(len(text))) for index, text in enumerate(texts))

    monkeypatch.setattr(
        "zsper.rag.embeddings._sentence_transformer_class",
        lambda: FakeSentenceTransformer,
        raising=False,
    )
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
    assert constructed_models == [
        (
            "sentence-transformers/all-MiniLM-L6-v2",
            {"local_files_only": True, "trust_remote_code": False},
        )
    ]
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
