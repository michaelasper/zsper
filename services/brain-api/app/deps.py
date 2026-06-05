"""Dependency helpers for the Brain API service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from fastapi import Depends, Request

from zsper.brain.api import (
    ApiProfileContext,
    DatabaseRuntimeConfig,
    ServiceProbes,
    resolve_api_profile_context,
)
from zsper.brain.redis import RedisRuntimeConfig, redis_config_from_env
from zsper.rag import HybridSearchEngine, ProfileRagStore
from zsper.rag.embeddings import EmbeddingProvider, provider_for_profile
from zsper.rag.indexes import ProfileBm25Index, ProfileVectorIndex


def get_service_env(environ: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def get_request_service_env(request: Request) -> Mapping[str, str]:
    app_env = getattr(request.app.state, "environ", None)
    return get_service_env(app_env)


def get_profile_id(environ: Mapping[str, str] | None = None) -> str:
    env = get_service_env(environ)
    profile_id = env.get("ZSPER_PROFILE_ID")
    if not profile_id:
        raise RuntimeError("ZSPER_PROFILE_ID is required")
    return profile_id


def get_redis_config(environ: Mapping[str, str] | None = None) -> RedisRuntimeConfig:
    return redis_config_from_env(get_service_env(environ))


def get_profile_context(request: Request) -> ApiProfileContext:
    return resolve_api_profile_context(
        get_request_service_env(request),
        request_profile_id=(
            request.headers.get("X-Zsper-Profile-Id")
            or request.headers.get("X-Zsper-Profile")
        ),
        request_profile_root=request.headers.get("X-Zsper-Profile-Root"),
    )


def get_database_config(
    context: ApiProfileContext = Depends(get_profile_context),
) -> DatabaseRuntimeConfig:
    return context.database


def get_redis_runtime_config(
    context: ApiProfileContext = Depends(get_profile_context),
) -> RedisRuntimeConfig:
    return context.redis


def get_service_probes(request: Request) -> ServiceProbes:
    return request.app.state.service_probes


def get_rag_store(
    context: ApiProfileContext = Depends(get_profile_context),
) -> ProfileRagStore:
    sqlite_path = context.environ.get("ZSPER_RAG_SQLITE_PATH")
    if sqlite_path or context.profile.storage_backend == "sqlite-local":
        return ProfileRagStore.sqlite(
            sqlite_path or _profile_index_path(context, "rag.sqlite")
        )
    return ProfileRagStore.postgres_dsn(context.database.dsn)


def get_bm25_index(
    context: ApiProfileContext = Depends(get_profile_context),
) -> ProfileBm25Index:
    return ProfileBm25Index.sqlite(
        context.environ.get("ZSPER_BM25_SQLITE_PATH")
        or _profile_index_path(context, "bm25.sqlite")
    )


def get_vector_index(
    context: ApiProfileContext = Depends(get_profile_context),
) -> ProfileVectorIndex:
    sqlite_path = context.environ.get("ZSPER_VECTOR_SQLITE_PATH")
    if sqlite_path or context.profile.storage_backend == "sqlite-local":
        return ProfileVectorIndex.sqlite(
            sqlite_path or _profile_index_path(context, "vectors.sqlite")
        )
    return ProfileVectorIndex.postgres_dsn(context.database.dsn)


def get_query_embedding_provider(
    context: ApiProfileContext = Depends(get_profile_context),
) -> EmbeddingProvider:
    return provider_for_profile(context.profile)


def get_hybrid_search_engine(
    store: ProfileRagStore = Depends(get_rag_store),
    bm25_index: ProfileBm25Index = Depends(get_bm25_index),
    vector_index: ProfileVectorIndex = Depends(get_vector_index),
    query_embedding_provider: EmbeddingProvider = Depends(get_query_embedding_provider),
) -> HybridSearchEngine:
    return HybridSearchEngine(
        store=store,
        bm25_index=bm25_index,
        vector_index=vector_index,
        query_embedding_provider=query_embedding_provider,
    )


def _profile_index_path(context: ApiProfileContext, filename: str) -> Path:
    return Path(context.profile.root) / "brain" / "indexes" / filename
