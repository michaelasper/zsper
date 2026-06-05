"""Citation-grounded chat route for profile-scoped Brain API RAG records."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import (
    get_answer_endpoint,
    get_answer_model_client,
    get_hybrid_search_engine,
    get_profile_context,
    get_rag_store,
)
from zsper.brain.api import ApiError, ApiProfileContext
from zsper.config.model_endpoint import ModelEndpoint
from zsper.rag import (
    AnswerError,
    AnswerModelClient,
    DEFAULT_SEARCH_LIMIT,
    HybridSearchEngine,
    HybridSearchError,
    ProfileRagStore,
    answer_question,
)


router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    limit: int = Field(DEFAULT_SEARCH_LIMIT, ge=1, le=50)


@router.post("")
def chat(
    request: ChatRequest,
    context: ApiProfileContext = Depends(get_profile_context),
    store: ProfileRagStore = Depends(get_rag_store),
    engine: HybridSearchEngine = Depends(get_hybrid_search_engine),
    endpoint: ModelEndpoint = Depends(get_answer_endpoint),
    model_client: AnswerModelClient = Depends(get_answer_model_client),
) -> dict[str, object]:
    question = request.question.strip()
    try:
        results = engine.search(context.profile, question, limit=request.limit)
    except HybridSearchError as exc:
        raise ApiError(
            code="search_failed",
            message=str(exc),
            status_code=400,
            profile_id=context.profile_id,
            details={"question": question},
        ) from exc

    try:
        answer = answer_question(
            context.profile,
            store,
            question,
            results,
            endpoint=endpoint,
            model_client=model_client,
        )
    except AnswerError as exc:
        raise ApiError(
            code="answer_failed",
            message=str(exc),
            status_code=400,
            profile_id=context.profile_id,
            details={"question": question},
        ) from exc

    return {
        "profile_id": context.profile_id,
        "question": question,
        "limit": request.limit,
        "result_count": len(results),
        "answer": answer.to_dict(),
    }
