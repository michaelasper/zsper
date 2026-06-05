"""Citation-grounded answer generation over retrieved RAG context."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from zsper.config.model_endpoint import ModelEndpoint, endpoints_for_profile
from zsper.profiles import Profile
from zsper.rag.models import CitationAnchor, DocumentChunk
from zsper.rag.search import HybridSearchResult
from zsper.rag.store import ProfileRagStore, RagStoreError
from zsper.security.network_policy import NetworkPolicyError, check_network_policy


DEFAULT_ANSWER_TIMEOUT_SECONDS = 30.0
DEFAULT_ANSWER_TEMPERATURE = 0.0
DEFAULT_ANSWER_MAX_TOKENS = 1024


class AnswerError(ValueError):
    """Raised when a citation-grounded answer cannot be produced."""


class AnswerModelClient(Protocol):
    """Minimal local OpenAI-compatible chat completions client contract."""

    def create_chat_completion(
        self,
        *,
        url: str,
        payload: Mapping[str, object],
        timeout: float,
    ) -> Mapping[str, object]:
        """Create a chat completion and return the decoded JSON payload."""


@dataclass(frozen=True)
class AnswerCitation:
    document_id: str
    chunk_id: str
    citation_anchor_id: str
    source_path_or_url: str
    display_range: str | None
    text_preview: str
    citation_confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "citation_anchor_id": self.citation_anchor_id,
            "source_path_or_url": self.source_path_or_url,
            "display_range": self.display_range,
            "text_preview": self.text_preview,
            "citation_confidence": self.citation_confidence,
        }


@dataclass(frozen=True)
class AnswerResult:
    profile_id: str
    question: str
    text: str
    answer_confidence: float
    citations: tuple[AnswerCitation, ...]
    model: str

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "question": self.question,
            "text": self.text,
            "answer_confidence": self.answer_confidence,
            "citations": [citation.to_dict() for citation in self.citations],
            "model": self.model,
        }


@dataclass(frozen=True)
class _AnswerContext:
    citation: AnswerCitation
    text: str


class OpenAICompatibleAnswerModelClient:
    """HTTP client for the local OpenAI-compatible chat completions endpoint."""

    def create_chat_completion(
        self,
        *,
        url: str,
        payload: Mapping[str, object],
        timeout: float,
    ) -> Mapping[str, object]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError) as exc:
            raise AnswerError(f"model request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AnswerError("model response was not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise AnswerError("model response must be a JSON object")
        return decoded


def answer_question(
    profile: Profile,
    store: ProfileRagStore,
    question: str,
    retrieved_results: Sequence[HybridSearchResult],
    *,
    model_client: AnswerModelClient | None = None,
    endpoint: ModelEndpoint | None = None,
    timeout: float = DEFAULT_ANSWER_TIMEOUT_SECONDS,
) -> AnswerResult:
    normalized_question = _normalize_question(question)
    endpoint = endpoint or endpoints_for_profile(profile)[0]
    _require_local_endpoint(profile, endpoint)
    results = tuple(retrieved_results)
    if not results:
        raise AnswerError("retrieved context is required for answering")
    contexts_by_anchor_id = _answer_contexts_for_results(
        profile,
        store,
        results,
    )
    client = model_client or OpenAICompatibleAnswerModelClient()
    payload = _chat_completion_payload(
        endpoint,
        normalized_question,
        tuple(contexts_by_anchor_id.values()),
    )
    response = client.create_chat_completion(
        url=endpoint.chat_completions_url,
        payload=payload,
        timeout=timeout,
    )
    model_answer = _parse_model_answer(_extract_message_content(response))
    cited_anchor_ids = _citation_anchor_ids(model_answer.get("citation_anchor_ids"))
    if not cited_anchor_ids:
        raise AnswerError("model answer must cite at least one retrieved chunk")

    citations: list[AnswerCitation] = []
    for anchor_id in cited_anchor_ids:
        context = contexts_by_anchor_id.get(anchor_id)
        if context is None:
            raise AnswerError(
                f"model cited a citation anchor outside retrieved context: {anchor_id}"
            )
        citations.append(context.citation)

    answer_text = model_answer.get("answer")
    if not isinstance(answer_text, str) or not answer_text.strip():
        raise AnswerError("model answer must include a non-empty answer")

    return AnswerResult(
        profile_id=profile.name,
        question=normalized_question,
        text=answer_text.strip(),
        answer_confidence=_confidence(
            model_answer.get("answer_confidence"),
            field_name="answer_confidence",
        ),
        citations=tuple(citations),
        model=endpoint.model_id,
    )


def _normalize_question(question: str) -> str:
    if not isinstance(question, str) or not question.strip():
        raise AnswerError("question must be a non-empty string")
    return question.strip()


def _require_local_endpoint(profile: Profile, endpoint: ModelEndpoint) -> None:
    parsed = urlparse(endpoint.base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise AnswerError("model endpoint must be local")
    try:
        check_network_policy(
            profile.network_policy,
            endpoint.base_url,
            action="localhost-service",
        ).raise_for_status()
    except NetworkPolicyError as exc:
        raise AnswerError("model endpoint must be local") from exc


def _answer_contexts_for_results(
    profile: Profile,
    store: ProfileRagStore,
    results: tuple[HybridSearchResult, ...],
) -> dict[str, _AnswerContext]:
    contexts: dict[str, _AnswerContext] = {}
    for result in results:
        if result.profile_id != profile.name:
            raise AnswerError("retrieved result profile_id must match the profile")
        chunk = _require_result_chunk(profile, store, result)
        anchor = _require_result_anchor(profile, store, result, chunk)
        contexts[anchor.id] = _AnswerContext(
            citation=AnswerCitation(
                document_id=result.document_id,
                chunk_id=chunk.id,
                citation_anchor_id=anchor.id,
                source_path_or_url=anchor.source_path_or_url,
                display_range=anchor.display_range,
                text_preview=result.text_preview or _text_preview(chunk.text),
                citation_confidence=_citation_confidence(result.score),
            ),
            text=chunk.text,
        )
    return contexts


def _require_result_chunk(
    profile: Profile,
    store: ProfileRagStore,
    result: HybridSearchResult,
) -> DocumentChunk:
    try:
        document = store.get_document(profile, result.document_id)
        if document is None:
            raise AnswerError(
                f"retrieved document is missing: {result.document_id}"
            )
        chunks = store.list_chunks(profile, document.id)
    except RagStoreError as exc:
        raise AnswerError(str(exc)) from exc

    for chunk in chunks:
        if chunk.id == result.chunk_id:
            if chunk.citation_anchor_id != result.citation_anchor_id:
                raise AnswerError(
                    "retrieved chunk citation anchor does not match the search result"
                )
            return chunk
    raise AnswerError(f"retrieved chunk is missing: {result.chunk_id}")


def _require_result_anchor(
    profile: Profile,
    store: ProfileRagStore,
    result: HybridSearchResult,
    chunk: DocumentChunk,
) -> CitationAnchor:
    try:
        anchors = store.list_citation_anchors(profile, result.document_id)
    except RagStoreError as exc:
        raise AnswerError(str(exc)) from exc
    for anchor in anchors:
        if anchor.id == result.citation_anchor_id:
            if anchor.chunk_id != chunk.id:
                raise AnswerError(
                    "citation anchor does not point at the retrieved chunk"
                )
            return anchor
    raise AnswerError(
        f"retrieved chunk is missing citation anchor: {result.citation_anchor_id}"
    )


def _chat_completion_payload(
    endpoint: ModelEndpoint,
    question: str,
    contexts: tuple[_AnswerContext, ...],
) -> dict[str, object]:
    return {
        "model": endpoint.model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer only from the provided context. Return strict JSON "
                    "with keys answer, answer_confidence, and citation_anchor_ids. "
                    "citation_anchor_ids must contain only cited context anchor ids."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "context": [
                            {
                                "citation_anchor_id": context.citation.citation_anchor_id,
                                "document_id": context.citation.document_id,
                                "chunk_id": context.citation.chunk_id,
                                "source_path_or_url": (
                                    context.citation.source_path_or_url
                                ),
                                "display_range": context.citation.display_range,
                                "text_preview": context.citation.text_preview,
                                "text": context.text,
                            }
                            for context in contexts
                        ],
                    },
                    sort_keys=True,
                ),
            },
        ],
        "temperature": DEFAULT_ANSWER_TEMPERATURE,
        "max_tokens": min(DEFAULT_ANSWER_MAX_TOKENS, endpoint.output_limit),
        "stream": False,
    }


def _extract_message_content(response: Mapping[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, Sequence) or not choices:
        raise AnswerError("model response is missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise AnswerError("model response choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise AnswerError("model response choice is missing a message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AnswerError("model response message content must be non-empty")
    return content.strip()


def _parse_model_answer(content: str) -> Mapping[str, object]:
    try:
        data = json.loads(_strip_json_fence(content))
    except json.JSONDecodeError as exc:
        raise AnswerError(
            "model answer must be JSON with answer, answer_confidence, "
            "and citation_anchor_ids"
        ) from exc
    if not isinstance(data, Mapping):
        raise AnswerError("model answer must be a JSON object")
    return data


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _citation_anchor_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AnswerError("model answer citation_anchor_ids must be a list")
    anchor_ids: list[str] = []
    for raw_anchor_id in value:
        if not isinstance(raw_anchor_id, str) or not raw_anchor_id.strip():
            raise AnswerError("model answer citation anchor ids must be non-empty strings")
        anchor_id = raw_anchor_id.strip()
        if anchor_id not in anchor_ids:
            anchor_ids.append(anchor_id)
    return tuple(anchor_ids)


def _confidence(value: object, *, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise AnswerError(f"model answer {field_name} must be a number")
    confidence = float(value)
    if not math.isfinite(confidence):
        raise AnswerError(f"model answer {field_name} must be finite")
    if confidence < 0.0 or confidence > 1.0:
        raise AnswerError(f"model answer {field_name} must be between 0 and 1")
    return confidence


def _citation_confidence(score: float) -> float:
    try:
        confidence = float(score)
    except (TypeError, ValueError) as exc:
        raise AnswerError("retrieved result score must be numeric") from exc
    return max(0.0, min(1.0, confidence))


def _text_preview(text: str, *, limit: int = 240) -> str:
    preview = " ".join(text.split())
    if len(preview) <= limit:
        return preview
    return preview[: limit - 3].rstrip() + "..."


__all__ = [
    "AnswerCitation",
    "AnswerError",
    "AnswerModelClient",
    "AnswerResult",
    "OpenAICompatibleAnswerModelClient",
    "answer_question",
]
