"""Hybrid BM25 plus dense retrieval for profile-scoped RAG chunks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from zsper.profiles import Profile
from zsper.rag.embeddings import EmbeddingProvider
from zsper.rag.indexes import (
    Bm25IndexError,
    Bm25SearchResult,
    ProfileBm25Index,
    ProfileVectorIndex,
    VectorIndexError,
    VectorSearchResult,
)
from zsper.rag.models import CitationAnchor, Document, DocumentChunk
from zsper.rag.store import ProfileRagStore, RagStoreError


DEFAULT_SEARCH_LIMIT = 10
DEFAULT_POOL_FACTOR = 4
DEFAULT_BM25_WEIGHT = 0.6
DEFAULT_DENSE_WEIGHT = 0.4
TEXT_PREVIEW_CHARS = 240


class HybridSearchError(ValueError):
    """Raised when hybrid search cannot run for a valid local profile."""


@dataclass(frozen=True)
class HybridSearchResult:
    profile_id: str
    document_id: str
    chunk_id: str
    citation_anchor_id: str
    source_path_or_url: str
    score: float
    score_components: Mapping[str, float]
    text_preview: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "score_components",
            {key: float(value) for key, value in self.score_components.items()},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "citation_anchor_id": self.citation_anchor_id,
            "source_path_or_url": self.source_path_or_url,
            "score": self.score,
            "score_components": dict(self.score_components),
            "text_preview": self.text_preview,
        }


@dataclass
class _Candidate:
    profile_id: str
    document_id: str
    chunk_id: str
    bm25_score: float = 0.0
    dense_score: float = 0.0
    bm25_rank: int | None = None
    dense_rank: int | None = None
    text_preview: str | None = None


@dataclass(frozen=True)
class HybridSearchEngine:
    store: ProfileRagStore
    bm25_index: ProfileBm25Index
    vector_index: ProfileVectorIndex
    query_embedding_provider: EmbeddingProvider | None = None
    bm25_weight: float = DEFAULT_BM25_WEIGHT
    dense_weight: float = DEFAULT_DENSE_WEIGHT
    pool_factor: int = DEFAULT_POOL_FACTOR

    def __post_init__(self) -> None:
        if self.bm25_weight < 0.0 or self.dense_weight < 0.0:
            raise HybridSearchError("hybrid search weights must be non-negative")
        if self.bm25_weight == 0.0:
            raise HybridSearchError("BM25 weight must be greater than zero")
        if self.pool_factor <= 0:
            raise HybridSearchError("pool_factor must be a positive integer")

    def search(
        self,
        profile: Profile,
        query: str,
        *,
        query_vector: Sequence[float] | None = None,
        embedding_model: str | None = None,
        query_embedding_provider: EmbeddingProvider | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        bm25_limit: int | None = None,
        dense_limit: int | None = None,
    ) -> list[HybridSearchResult]:
        query = _normalize_query(query)
        limit = _normalize_limit(limit)
        pool_limit = max(limit, limit * self.pool_factor)
        bm25_results = self._search_bm25(
            profile,
            query,
            limit=bm25_limit or pool_limit,
        )
        dense_results = self._search_dense(
            profile,
            query,
            query_vector=query_vector,
            embedding_model=embedding_model,
            query_embedding_provider=query_embedding_provider,
            limit=dense_limit or pool_limit,
        )
        candidates = _merge_candidates(bm25_results, dense_results)
        ranked = _rank_candidates(
            candidates,
            bm25_weight=self.bm25_weight,
            dense_weight=self.dense_weight,
        )
        return self._resolve_candidates(profile, ranked, limit=limit)

    def _search_bm25(
        self,
        profile: Profile,
        query: str,
        *,
        limit: int,
    ) -> list[Bm25SearchResult]:
        try:
            return self.bm25_index.search(profile, query, limit=limit)
        except Bm25IndexError as exc:
            raise HybridSearchError(str(exc)) from exc

    def _search_dense(
        self,
        profile: Profile,
        query: str,
        *,
        query_vector: Sequence[float] | None,
        embedding_model: str | None,
        query_embedding_provider: EmbeddingProvider | None,
        limit: int,
    ) -> list[VectorSearchResult]:
        provider = query_embedding_provider or self.query_embedding_provider
        if query_vector is None:
            if provider is None:
                return []
            query_vector = _embed_query(provider, query)
            embedding_model = embedding_model or provider.model
        embedding_model = embedding_model or profile.embedding_profile
        try:
            return self.vector_index.search(
                profile,
                query_vector=query_vector,
                embedding_model=embedding_model,
                limit=limit,
            )
        except VectorIndexError as exc:
            raise HybridSearchError(f"dense vector search failed: {exc}") from exc

    def _resolve_candidates(
        self,
        profile: Profile,
        ranked_candidates: Sequence[tuple[_Candidate, float]],
        *,
        limit: int,
    ) -> list[HybridSearchResult]:
        resolved: list[HybridSearchResult] = []
        document_cache: dict[str, Document | None] = {}
        chunk_cache: dict[tuple[str, str], DocumentChunk | None] = {}
        anchor_cache: dict[tuple[str, str], CitationAnchor | None] = {}
        for candidate, score in ranked_candidates:
            document = _cached_document(
                self.store,
                profile,
                candidate.document_id,
                document_cache,
            )
            if document is None:
                continue
            chunk = _cached_chunk(
                self.store,
                profile,
                document.id,
                candidate.chunk_id,
                chunk_cache,
            )
            if chunk is None:
                continue
            anchor = _cached_anchor(
                self.store,
                profile,
                document.id,
                chunk.citation_anchor_id,
                anchor_cache,
            )
            resolved.append(
                HybridSearchResult(
                    profile_id=profile.name,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    citation_anchor_id=chunk.citation_anchor_id,
                    source_path_or_url=_source_path_or_url(document, anchor),
                    score=score,
                    score_components={
                        "bm25": candidate.bm25_score,
                        "dense": candidate.dense_score,
                    },
                    text_preview=candidate.text_preview or _text_preview(chunk.text),
                )
            )
            if len(resolved) >= limit:
                break
        return resolved


def hybrid_search(
    profile: Profile,
    query: str,
    *,
    store: ProfileRagStore,
    bm25_index: ProfileBm25Index,
    vector_index: ProfileVectorIndex,
    query_vector: Sequence[float] | None = None,
    embedding_model: str | None = None,
    query_embedding_provider: EmbeddingProvider | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[HybridSearchResult]:
    engine = HybridSearchEngine(
        store=store,
        bm25_index=bm25_index,
        vector_index=vector_index,
        query_embedding_provider=query_embedding_provider,
    )
    return engine.search(
        profile,
        query,
        query_vector=query_vector,
        embedding_model=embedding_model,
        limit=limit,
    )


def _normalize_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise HybridSearchError("search query must be a non-empty string")
    return query.strip()


def _normalize_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise HybridSearchError("search limit must be a positive integer")
    return limit


def _embed_query(
    provider: EmbeddingProvider,
    query: str,
) -> tuple[float, ...]:
    vectors = tuple(provider.embed_texts([query]))
    if len(vectors) != 1:
        raise HybridSearchError("query embedding provider returned the wrong count")
    return tuple(float(value) for value in vectors[0])


def _merge_candidates(
    bm25_results: Sequence[Bm25SearchResult],
    dense_results: Sequence[VectorSearchResult],
) -> list[_Candidate]:
    candidates: dict[tuple[str, str, str], _Candidate] = {}
    for rank, result in enumerate(bm25_results):
        key = (result.profile_id, result.document_id, result.chunk_id)
        candidate = candidates.setdefault(
            key,
            _Candidate(
                profile_id=result.profile_id,
                document_id=result.document_id,
                chunk_id=result.chunk_id,
            ),
        )
        candidate.bm25_score = max(0.0, float(result.score))
        candidate.bm25_rank = rank
        candidate.text_preview = result.text_preview

    for rank, result in enumerate(dense_results):
        key = (result.profile_id, result.document_id, result.chunk_id)
        candidate = candidates.setdefault(
            key,
            _Candidate(
                profile_id=result.profile_id,
                document_id=result.document_id,
                chunk_id=result.chunk_id,
            ),
        )
        candidate.dense_score = float(result.score)
        candidate.dense_rank = rank

    return list(candidates.values())


def _rank_candidates(
    candidates: Sequence[_Candidate],
    *,
    bm25_weight: float,
    dense_weight: float,
) -> list[tuple[_Candidate, float]]:
    max_bm25 = max((candidate.bm25_score for candidate in candidates), default=0.0)
    max_dense = max(
        (max(0.0, candidate.dense_score) for candidate in candidates),
        default=0.0,
    )
    ranked = [
        (
            candidate,
            bm25_weight * _normalize_score(candidate.bm25_score, max_bm25)
            + dense_weight
            * _normalize_score(max(0.0, candidate.dense_score), max_dense),
        )
        for candidate in candidates
    ]
    ranked.sort(
        key=lambda item: (
            -item[1],
            item[0].bm25_rank is None,
            item[0].bm25_rank if item[0].bm25_rank is not None else 1_000_000,
            item[0].dense_rank is None,
            item[0].dense_rank if item[0].dense_rank is not None else 1_000_000,
            item[0].document_id,
            item[0].chunk_id,
        )
    )
    return ranked


def _normalize_score(score: float, max_score: float) -> float:
    if max_score <= 0.0:
        return 0.0
    return score / max_score


def _cached_document(
    store: ProfileRagStore,
    profile: Profile,
    document_id: str,
    cache: dict[str, Document | None],
) -> Document | None:
    if document_id not in cache:
        try:
            cache[document_id] = store.get_document(profile, document_id)
        except RagStoreError as exc:
            raise HybridSearchError(str(exc)) from exc
    return cache[document_id]


def _cached_chunk(
    store: ProfileRagStore,
    profile: Profile,
    document_id: str,
    chunk_id: str,
    cache: dict[tuple[str, str], DocumentChunk | None],
) -> DocumentChunk | None:
    key = (document_id, chunk_id)
    if key not in cache:
        try:
            cache[key] = next(
                (
                    chunk
                    for chunk in store.list_chunks(profile, document_id)
                    if chunk.id == chunk_id
                ),
                None,
            )
        except RagStoreError as exc:
            raise HybridSearchError(str(exc)) from exc
    return cache[key]


def _cached_anchor(
    store: ProfileRagStore,
    profile: Profile,
    document_id: str,
    anchor_id: str,
    cache: dict[tuple[str, str], CitationAnchor | None],
) -> CitationAnchor | None:
    key = (document_id, anchor_id)
    if key not in cache:
        try:
            cache[key] = next(
                (
                    anchor
                    for anchor in store.list_citation_anchors(profile, document_id)
                    if anchor.id == anchor_id
                ),
                None,
            )
        except RagStoreError as exc:
            raise HybridSearchError(str(exc)) from exc
    return cache[key]


def _source_path_or_url(document: Document, anchor: CitationAnchor | None) -> str:
    if anchor is not None:
        return anchor.source_path_or_url
    for key in ("original_url", "final_url", "original_path", "source_path"):
        value = document.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return document.raw_asset_path


def _text_preview(text: str) -> str:
    preview = " ".join(text.split())
    if len(preview) <= TEXT_PREVIEW_CHARS:
        return preview
    return preview[: TEXT_PREVIEW_CHARS - 3].rstrip() + "..."
