"""Local embedding metadata worker for profile-scoped RAG chunks."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
DEFAULT_LOCAL_EMBEDDING_MODEL_REFS = {
    "local-bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
    "local-small-embedding": "sentence-transformers/all-MiniLM-L6-v2",
}
DEFAULT_EMBEDDING_BATCH_SIZE = 32


class EmbeddingError(ValueError):
    """Raised when local embedding generation cannot proceed."""


class EmbeddingProvider(Protocol):
    """Provider interface for local embedding implementations."""

    model: str

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one embedding vector for each input text."""


class EmbeddingWorker(Protocol):
    """Worker interface for concrete local embedding runtimes."""

    def embed_texts(
        self,
        model: str,
        texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        """Return vectors for one bounded batch of text."""


@dataclass(frozen=True)
class LocalEmbeddingProvider:
    """Profile-scoped local provider backed by a real local embedding worker."""

    model: str
    worker: EmbeddingWorker | None = None
    batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE

    def __post_init__(self) -> None:
        _validate_local_model(self.model)
        if not isinstance(self.batch_size, int) or isinstance(self.batch_size, bool):
            raise EmbeddingError("embedding batch_size must be a positive integer")
        if self.batch_size <= 0:
            raise EmbeddingError("embedding batch_size must be a positive integer")
        if self.worker is None:
            object.__setattr__(self, "worker", SentenceTransformerEmbeddingWorker())

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        worker = self.worker
        if worker is None:
            raise EmbeddingError("embedding provider worker is not configured")

        vectors: list[tuple[float, ...]] = []
        for batch in _batched(tuple(texts), self.batch_size):
            batch_vectors = _coerce_vectors(worker.embed_texts(self.model, batch), len(batch))
            vectors.extend(batch_vectors)
        return tuple(vectors)


@dataclass(frozen=True)
class SentenceTransformerEmbeddingWorker:
    """Local SentenceTransformers worker with network downloads disabled."""

    model_refs: Mapping[str, str] | None = None
    device: str | None = None
    _loaded_models: dict[tuple[str, str, str | None, type[Any]], Any] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    def ensure_runtime_available(self) -> None:
        _sentence_transformer_class()

    def embed_texts(
        self,
        model: str,
        texts: Sequence[str],
    ) -> tuple[tuple[float, ...], ...]:
        _validate_local_model(model)
        model_ref = _model_ref_for_profile(model, self.model_refs)
        sentence_transformer = self._loaded_model(model, model_ref)
        try:
            raw_vectors = sentence_transformer.encode(
                list(texts),
                batch_size=max(1, len(texts)),
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=False,
            )
        except Exception as exc:
            raise EmbeddingError(
                f"local embedding generation failed for embedding_profile {model!r}: {exc}"
            ) from exc
        return _coerce_vectors(raw_vectors, len(texts))

    def _loaded_model(self, profile_model: str, model_ref: str) -> Any:
        sentence_transformer_class = _sentence_transformer_class()
        cache_key = (
            profile_model,
            model_ref,
            self.device,
            sentence_transformer_class,
        )
        model = self._loaded_models.get(cache_key)
        if model is None:
            model = _load_sentence_transformer_model(
                profile_model,
                model_ref,
                self.device,
                sentence_transformer_class,
            )
            self._loaded_models[cache_key] = model
        return model


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


_DEFAULT_SENTENCE_TRANSFORMER_WORKER = SentenceTransformerEmbeddingWorker()


def provider_for_profile(
    profile: Profile,
    *,
    settings: Mapping[str, Any] | None = None,
) -> EmbeddingProvider:
    """Create the default local provider for a profile after policy validation."""

    if settings is not None:
        validate_embedding_settings(profile, settings)
    model_refs = _embedding_model_refs_from_settings(settings)
    worker = (
        _DEFAULT_SENTENCE_TRANSFORMER_WORKER
        if model_refs is None
        else SentenceTransformerEmbeddingWorker(model_refs=model_refs)
    )
    worker.ensure_runtime_available()
    return LocalEmbeddingProvider(
        model=profile.embedding_profile,
        worker=worker,
        batch_size=_embedding_batch_size_from_settings(settings),
    )


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
    return _coerce_vectors(provider.embed_texts(texts), len(texts))


def _coerce_vectors(
    vectors: Sequence[Sequence[float]],
    expected_count: int,
) -> tuple[tuple[float, ...], ...]:
    coerced = tuple(tuple(float(value) for value in vector) for vector in vectors)
    if len(coerced) != expected_count:
        raise EmbeddingError("embedding provider returned the wrong vector count")

    dimensions: int | None = None
    for vector in coerced:
        if not vector:
            raise EmbeddingError("embedding provider returned an empty vector")
        if any(not math.isfinite(value) for value in vector):
            raise EmbeddingError("embedding provider returned a non-finite vector value")
        if dimensions is None:
            dimensions = len(vector)
        elif len(vector) != dimensions:
            raise EmbeddingError("embedding provider returned inconsistent dimensions")
    return coerced


def _batched(
    values: Sequence[str],
    batch_size: int,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(values[index : index + batch_size])
        for index in range(0, len(values), batch_size)
    )


def _sentence_transformer_class() -> type[Any]:
    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as exc:
        raise EmbeddingError(
            "local embedding runtime unavailable: install SentenceTransformers with "
            "`uv sync --group rag` and cache the embedding model locally before "
            "running default RAG embeddings"
        ) from exc
    return SentenceTransformer


def _load_sentence_transformer_model(
    profile_model: str,
    model_ref: str,
    device: str | None,
    sentence_transformer_class: type[Any],
) -> Any:
    kwargs: dict[str, object] = {
        "local_files_only": True,
        "trust_remote_code": False,
    }
    if device:
        kwargs["device"] = device
    try:
        return sentence_transformer_class(model_ref, **kwargs)
    except Exception as exc:
        env_name = _embedding_model_env_name(profile_model)
        raise EmbeddingError(
            "local embedding model unavailable for embedding_profile "
            f"{profile_model!r} using {model_ref!r}: cache the model locally or set "
            f"{env_name} to a local model directory; downloads are disabled"
        ) from exc


def _model_ref_for_profile(
    model: str,
    model_refs: Mapping[str, str] | None,
) -> str:
    configured_ref = None if model_refs is None else model_refs.get(model)
    env_ref = os.environ.get(_embedding_model_env_name(model))
    global_env_ref = os.environ.get("ZSPER_EMBEDDING_MODEL_PATH")
    model_ref = env_ref or configured_ref or global_env_ref
    if model_ref is None:
        model_ref = DEFAULT_LOCAL_EMBEDDING_MODEL_REFS[model]
    if _is_http_url(model_ref):
        raise EmbeddingError(
            "embedding model reference must be a local path or local cache id, not a URL"
        )
    return model_ref


def _embedding_model_refs_from_settings(
    settings: Mapping[str, Any] | None,
) -> Mapping[str, str] | None:
    if settings is None:
        return None
    configured = settings.get("embedding_models")
    if not isinstance(configured, Mapping):
        return None

    refs: dict[str, str] = {}
    for model, raw_value in configured.items():
        if not isinstance(model, str):
            continue
        _validate_local_model(model)
        if isinstance(raw_value, str):
            refs[model] = raw_value
            continue
        if isinstance(raw_value, Mapping):
            raw_ref = raw_value.get("model_path") or raw_value.get("model_ref")
            if isinstance(raw_ref, str):
                refs[model] = raw_ref
    return refs


def _embedding_batch_size_from_settings(settings: Mapping[str, Any] | None) -> int:
    if settings is None:
        return DEFAULT_EMBEDDING_BATCH_SIZE
    raw_batch_size = settings.get("embedding_batch_size")
    if raw_batch_size is None:
        return DEFAULT_EMBEDDING_BATCH_SIZE
    if not isinstance(raw_batch_size, int) or isinstance(raw_batch_size, bool):
        raise EmbeddingError("embedding_batch_size must be a positive integer")
    if raw_batch_size <= 0:
        raise EmbeddingError("embedding_batch_size must be a positive integer")
    return raw_batch_size


def _embedding_model_env_name(model: str) -> str:
    suffix = "".join(character if character.isalnum() else "_" for character in model)
    return f"ZSPER_EMBEDDING_MODEL_PATH_{suffix.upper()}"


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
