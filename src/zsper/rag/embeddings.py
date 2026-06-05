"""Local embedding metadata worker for profile-scoped RAG chunks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from zsper.profiles import Profile
from zsper.rag.models import DocumentChunk
from zsper.rag.policy import RagPolicyGate
from zsper.rag.store import ProfileRagStore


DEFAULT_EMBEDDING_DIMENSIONS = 384
SUPPORTED_LOCAL_EMBEDDING_PROFILES = frozenset(
    {
        "local-bge-small-en-v1.5",
        "local-small-embedding",
    }
)


class EmbeddingError(ValueError):
    """Raised when local embedding generation cannot proceed."""


class EmbeddingProvider(Protocol):
    """Provider interface for local embedding implementations."""

    model: str

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one embedding vector for each input text."""


@dataclass(frozen=True)
class LocalEmbeddingProvider:
    """Deterministic local provider used when no external model process is injected."""

    model: str
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS

    def __post_init__(self) -> None:
        _validate_local_model(self.model)
        if not isinstance(self.dimensions, int) or isinstance(self.dimensions, bool):
            raise EmbeddingError("embedding dimensions must be a positive integer")
        if self.dimensions <= 0:
            raise EmbeddingError("embedding dimensions must be a positive integer")

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(
            _deterministic_vector(self.model, text, self.dimensions) for text in texts
        )


@dataclass(frozen=True)
class DeterministicFakeEmbeddingProvider:
    """Small deterministic provider intended for unit tests."""

    model: str

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise EmbeddingError("embedding provider model must be a non-empty string")

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(
            (
                float(index),
                float(len(text)),
                float(sum(text.encode("utf-8")) % 997),
            )
            for index, text in enumerate(texts)
        )


@dataclass(frozen=True)
class EmbeddingRecord:
    chunk_id: str
    embedding_model: str
    vector_id: str
    dimensions: int


@dataclass(frozen=True)
class EmbeddingResult:
    document_id: str
    embedding_model: str
    chunk_count: int
    vector_ids: tuple[str, ...]
    vectors: tuple[tuple[float, ...], ...]
    records: tuple[EmbeddingRecord, ...]


def provider_for_profile(
    profile: Profile,
    *,
    settings: Mapping[str, Any] | None = None,
) -> EmbeddingProvider:
    """Create the default local provider for a profile after policy validation."""

    if settings is not None:
        validate_embedding_settings(profile, settings)
    return LocalEmbeddingProvider(model=profile.embedding_profile)


def validate_embedding_settings(profile: Profile, settings: Mapping[str, Any]) -> None:
    """Reject settings that would route embeddings outside local policy bounds."""

    gate = RagPolicyGate(profile)
    gate.require_no_hosted_settings(settings)
    for target in sorted(set(_iter_setting_urls(settings))):
        gate.require_action(target, action="localhost-service")


def embed_chunks(
    profile: Profile,
    store: ProfileRagStore,
    document_id: str,
    *,
    provider: EmbeddingProvider | None = None,
) -> EmbeddingResult:
    """Generate embeddings for existing chunks and persist their metadata."""

    provider = provider or provider_for_profile(profile)
    _validate_provider_model(profile, provider.model)

    chunks = tuple(store.list_chunks(profile, document_id))
    vectors = _embed_texts(provider, [chunk.text for chunk in chunks])
    records: list[EmbeddingRecord] = []
    vector_ids: list[str] = []

    for chunk, vector in zip(chunks, vectors, strict=True):
        vector_id = embedding_vector_id(
            profile,
            document_id=document_id,
            chunk=chunk,
            model=provider.model,
        )
        store.upsert_chunk(
            profile,
            DocumentChunk(
                **{
                    **chunk.to_dict(),
                    "embedding_model": provider.model,
                    "embedding_vector_id": vector_id,
                }
            ),
        )
        vector_ids.append(vector_id)
        records.append(
            EmbeddingRecord(
                chunk_id=chunk.id,
                embedding_model=provider.model,
                vector_id=vector_id,
                dimensions=len(vector),
            )
        )

    return EmbeddingResult(
        document_id=document_id,
        embedding_model=provider.model,
        chunk_count=len(chunks),
        vector_ids=tuple(vector_ids),
        vectors=vectors,
        records=tuple(records),
    )


def embedding_vector_id(
    profile: Profile,
    *,
    document_id: str,
    chunk: DocumentChunk,
    model: str,
) -> str:
    """Return the stable vector identity for chunk text and embedding model."""

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


def _validate_provider_model(profile: Profile, model: str) -> None:
    _validate_local_model(model)
    if model != profile.embedding_profile:
        raise EmbeddingError(
            "embedding provider model must match profile embedding_profile"
        )


def _validate_local_model(model: str) -> None:
    if model not in SUPPORTED_LOCAL_EMBEDDING_PROFILES:
        raise EmbeddingError(f"unsupported local embedding_profile: {model}")


def _embed_texts(
    provider: EmbeddingProvider,
    texts: Sequence[str],
) -> tuple[tuple[float, ...], ...]:
    vectors = tuple(tuple(float(value) for value in vector) for vector in provider.embed_texts(texts))
    if len(vectors) != len(texts):
        raise EmbeddingError("embedding provider returned the wrong vector count")
    return vectors


def _deterministic_vector(model: str, text: str, dimensions: int) -> tuple[float, ...]:
    values: list[float] = []
    counter = 0
    text_bytes = text.encode("utf-8")
    model_bytes = model.encode("utf-8")
    while len(values) < dimensions:
        block = hashlib.sha256(
            model_bytes + b"\0" + str(counter).encode("ascii") + b"\0" + text_bytes
        ).digest()
        for offset in range(0, len(block), 4):
            integer = int.from_bytes(block[offset : offset + 4], "big")
            values.append((integer / 0xFFFFFFFF) * 2.0 - 1.0)
            if len(values) == dimensions:
                break
        counter += 1
    return tuple(values)


def _iter_setting_urls(value: Any) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        urls: list[str] = []
        for child in value.values():
            urls.extend(_iter_setting_urls(child))
        return tuple(urls)
    if isinstance(value, (list, tuple, set, frozenset)):
        urls = []
        for child in value:
            urls.extend(_iter_setting_urls(child))
        return tuple(urls)
    if isinstance(value, str) and _is_http_url(value):
        return (value,)
    return ()


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}
