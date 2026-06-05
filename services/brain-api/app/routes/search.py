"""Hybrid search route for profile-scoped Brain API RAG records."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.deps import get_hybrid_search_engine, get_profile_context
from zsper.brain.api import ApiError, ApiProfileContext
from zsper.rag import DEFAULT_SEARCH_LIMIT, HybridSearchEngine, HybridSearchError


router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    query: str = Query(..., min_length=1),
    limit: int = Query(DEFAULT_SEARCH_LIMIT, ge=1, le=50),
    context: ApiProfileContext = Depends(get_profile_context),
    engine: HybridSearchEngine = Depends(get_hybrid_search_engine),
) -> dict[str, object]:
    try:
        results = engine.search(context.profile, query, limit=limit)
    except HybridSearchError as exc:
        raise ApiError(
            code="search_failed",
            message=str(exc),
            status_code=400,
            profile_id=context.profile_id,
            details={"query": query},
        ) from exc

    return {
        "profile_id": context.profile_id,
        "query": query,
        "limit": limit,
        "result_count": len(results),
        "results": [result.to_dict() for result in results],
    }
