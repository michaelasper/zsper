from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag import CitationAnchor, Document, DocumentChunk, ProfileRagStore
from zsper.rag.indexes import ProfileBm25Index, ProfileVectorIndex
from zsper.rag.search import HybridSearchResult


SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services" / "brain-api"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


class _FakeAnswerModelClient:
    def __init__(
        self,
        *,
        content: str,
    ) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def create_chat_completion(
        self,
        *,
        url: str,
        payload: Mapping[str, object],
        timeout: float,
    ) -> Mapping[str, object]:
        self.calls.append(
            {
                "url": url,
                "payload": dict(payload),
                "timeout": timeout,
            }
        )
        return {
            "choices": [
                {
                    "message": {
                        "content": self.content,
                    }
                }
            ]
        }


class _StaticQueryEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str,
        vectors_by_text: dict[str, Sequence[float]],
    ) -> None:
        self.model = model
        self._vectors_by_text = vectors_by_text

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(
            tuple(float(value) for value in self._vectors_by_text[text])
            for text in texts
        )


def _document(profile: Profile, parsed_path: Path) -> Document:
    return Document(
        id="doc-answer",
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(parsed_path.with_suffix(".raw")),
        parsed_representation_path=str(parsed_path),
        title="Answer Fixture",
        metadata={
            "original_path": str(parsed_path.with_suffix(".source")),
            "source_name": parsed_path.name,
        },
        content_hash=f"sha256:{profile.name}:doc-answer",
        parser="text",
        created_at="2026-06-04T12:00:00+00:00",
        updated_at="2026-06-04T12:00:00+00:00",
    )


def _chunk(
    *,
    document_id: str = "doc-answer",
    chunk_id: str = "chunk-answer",
    text: str = (
        "Restart the worker from the profile runtime directory and verify "
        "status before closing the incident."
    ),
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        chunk_index=0,
        text=text,
        citation_anchor_id=f"anchor-{chunk_id}",
        token_estimate=max(1, len(text.split())),
        byte_start=12,
        byte_end=12 + len(text.encode("utf-8")),
        embedding_model="local-bge-small-en-v1.5",
        embedding_vector_id=f"vec-{chunk_id}",
    )


def _anchor(
    document: Document,
    chunk: DocumentChunk,
    *,
    source_path_or_url: str | None = None,
) -> CitationAnchor:
    return CitationAnchor(
        id=chunk.citation_anchor_id,
        document_id=document.id,
        chunk_id=chunk.id,
        label=f"{document.title} chunk {chunk.chunk_index + 1}",
        source_path_or_url=source_path_or_url or str(
            Path(document.parsed_representation_path).with_suffix(".source")
        ),
        display_range=f"bytes {chunk.byte_start}-{chunk.byte_end}",
    )


def _search_result(
    profile: Profile,
    document: Document,
    chunk: DocumentChunk,
    *,
    score: float = 0.82,
) -> HybridSearchResult:
    return HybridSearchResult(
        profile_id=profile.name,
        document_id=document.id,
        chunk_id=chunk.id,
        citation_anchor_id=chunk.citation_anchor_id,
        source_path_or_url=str(
            Path(document.parsed_representation_path).with_suffix(".source")
        ),
        score=score,
        score_components={"bm25": score, "dense": 0.0},
        text_preview="Restart the worker from the profile runtime directory.",
    )


def _store_with_answer_fixture(
    tmp_path: Path,
    profile: Profile,
    *,
    persist_anchor: bool = True,
    chunk_text: str | None = None,
) -> tuple[ProfileRagStore, Document, DocumentChunk, CitationAnchor]:
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    parsed_path = Path(profile.root) / "brain" / "parsed" / "answer.txt"
    document = _document(profile, parsed_path)
    chunk = _chunk(
        document_id=document.id,
        text=chunk_text
        or (
            "Restart the worker from the profile runtime directory and verify "
            "status before closing the incident."
        ),
    )
    anchor = _anchor(document, chunk)
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)
    if persist_anchor:
        store.upsert_citation_anchor(profile, anchor)
    return store, document, chunk, anchor


def _model_json(
    *,
    answer: str = "Restart the worker from the profile runtime directory.",
    answer_confidence: float = 0.74,
    citation_anchor_ids: list[str],
) -> str:
    return json.dumps(
        {
            "answer": answer,
            "answer_confidence": answer_confidence,
            "citation_anchor_ids": citation_anchor_ids,
        }
    )


def _service_env(
    profile: Profile,
    registry_path: Path,
    *,
    rag_db_path: Path,
    bm25_db_path: Path,
    vector_db_path: Path,
) -> dict[str, str]:
    return {
        "ZSPER_PROFILE_ID": profile.name,
        "ZSPER_PROFILE_ROOT": profile.root,
        "ZSPER_PROFILE_REGISTRY": str(registry_path),
        "ZSPER_RAG_SQLITE_PATH": str(rag_db_path),
        "ZSPER_BM25_SQLITE_PATH": str(bm25_db_path),
        "ZSPER_VECTOR_SQLITE_PATH": str(vector_db_path),
        "POSTGRES_DB": profile.database_name,
        "POSTGRES_DSN": f"postgresql://zsper:local@127.0.0.1/{profile.database_name}",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_KEY_PREFIX": f"zsper:{profile.name}:",
        "ZSPER_MODEL_BASE_URL": "http://127.0.0.1:9127/v1",
    }


def test_answer_question_returns_model_text_with_exact_citation_objects(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.answer import AnswerResult, answer_question

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store, document, chunk, anchor = _store_with_answer_fixture(tmp_path, profile)
    result = _search_result(profile, document, chunk)
    model_client = _FakeAnswerModelClient(
        content=_model_json(
            answer="Restart the worker from the profile runtime directory.",
            answer_confidence=0.74,
            citation_anchor_ids=[anchor.id],
        )
    )

    answer = answer_question(
        profile,
        store,
        "How should I recover the worker?",
        [result],
        model_client=model_client,
    )

    assert isinstance(answer, AnswerResult)
    assert answer.text == "Restart the worker from the profile runtime directory."
    assert answer.answer_confidence == 0.74
    assert len(answer.citations) == 1
    citation = answer.citations[0]
    assert citation.document_id == document.id
    assert citation.chunk_id == chunk.id
    assert citation.citation_anchor_id == anchor.id
    assert citation.source_path_or_url == anchor.source_path_or_url
    assert citation.display_range == anchor.display_range
    assert citation.text_preview == result.text_preview
    assert citation.citation_confidence == result.score
    assert citation.citation_confidence != answer.answer_confidence
    assert answer.to_dict()["citations"] == [citation.to_dict()]
    assert model_client.calls[0]["url"] == "http://127.0.0.1:9127/v1/chat/completions"
    assert model_client.calls[0]["payload"]["model"] == profile.model_profile
    assert model_client.calls[0]["payload"]["messages"][0]["role"] == "system"
    assert "anchor-chunk-answer" in json.dumps(
        model_client.calls[0]["payload"]["messages"]
    )


def test_answer_question_sends_full_chunk_text_but_returns_preview(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.answer import answer_question

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    long_chunk_text = (
        "Early operational notes that are visible in the search preview. "
        + ("background filler " * 40)
        + "The precise remediation is to rotate the local Redis key prefix "
        "after the profile migration completes."
    )
    store, document, chunk, anchor = _store_with_answer_fixture(
        tmp_path,
        profile,
        chunk_text=long_chunk_text,
    )
    result = _search_result(profile, document, chunk)
    model_client = _FakeAnswerModelClient(
        content=_model_json(
            answer="Rotate the local Redis key prefix after migration.",
            answer_confidence=0.81,
            citation_anchor_ids=[anchor.id],
        )
    )

    answer = answer_question(
        profile,
        store,
        "What should I rotate after migration?",
        [result],
        model_client=model_client,
    )

    user_message = model_client.calls[0]["payload"]["messages"][1]
    prompt = json.loads(user_message["content"])
    context = prompt["context"][0]
    assert context["text"] == long_chunk_text
    assert context["text_preview"] == result.text_preview
    assert "Redis key prefix" in context["text"]
    assert "Redis key prefix" not in answer.citations[0].text_preview


def test_answer_question_fails_without_retrieved_context_before_model_call(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.answer import AnswerError, answer_question

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    model_client = _FakeAnswerModelClient(content=_model_json(citation_anchor_ids=[]))

    with pytest.raises(AnswerError, match="retrieved context is required"):
        answer_question(
            profile,
            store,
            "How should I recover the worker?",
            [],
            model_client=model_client,
        )

    assert model_client.calls == []


def test_answer_question_fails_when_retrieved_chunk_has_no_stored_citation(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.answer import AnswerError, answer_question

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store, document, chunk, anchor = _store_with_answer_fixture(
        tmp_path,
        profile,
        persist_anchor=False,
    )
    model_client = _FakeAnswerModelClient(
        content=_model_json(citation_anchor_ids=[anchor.id])
    )

    with pytest.raises(AnswerError, match="missing citation anchor"):
        answer_question(
            profile,
            store,
            "How should I recover the worker?",
            [_search_result(profile, document, chunk)],
            model_client=model_client,
        )

    assert model_client.calls == []


def test_answer_question_fails_when_model_omits_citations_for_retrieved_context(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from zsper.rag.answer import AnswerError, answer_question

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store, document, chunk, _anchor_record = _store_with_answer_fixture(
        tmp_path,
        profile,
    )
    model_client = _FakeAnswerModelClient(
        content=_model_json(citation_anchor_ids=[])
    )

    with pytest.raises(AnswerError, match="must cite at least one retrieved chunk"):
        answer_question(
            profile,
            store,
            "How should I recover the worker?",
            [_search_result(profile, document, chunk)],
            model_client=model_client,
        )


def test_chat_api_route_returns_structured_citation_objects(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    from app.deps import get_answer_model_client, get_query_embedding_provider
    from app.main import create_app

    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    rag_db_path = tmp_path / "rag.sqlite"
    bm25_db_path = tmp_path / "bm25.sqlite"
    vector_db_path = tmp_path / "vectors.sqlite"
    store = ProfileRagStore.sqlite(rag_db_path)
    bm25_index = ProfileBm25Index.sqlite(bm25_db_path)
    vector_index = ProfileVectorIndex.sqlite(vector_db_path)
    parsed_path = Path(profile.root) / "brain" / "parsed" / "answer.txt"
    document = _document(profile, parsed_path)
    chunk = _chunk(document_id=document.id)
    anchor = _anchor(document, chunk)
    store.upsert_document(profile, document)
    store.upsert_chunk(profile, chunk)
    store.upsert_citation_anchor(profile, anchor)
    bm25_index.index_chunks(profile, document, [chunk])
    vector_index.index_chunks(
        profile,
        document,
        [chunk],
        vectors_by_chunk_id={chunk.id: (1.0, 0.0, 0.0)},
    )
    app = create_app(
        environ=_service_env(
            profile,
            isolated_registry_path,
            rag_db_path=rag_db_path,
            bm25_db_path=bm25_db_path,
            vector_db_path=vector_db_path,
        )
    )
    fake_model = _FakeAnswerModelClient(
        content=_model_json(citation_anchor_ids=[anchor.id])
    )
    app.dependency_overrides[get_query_embedding_provider] = lambda: (
        _StaticQueryEmbeddingProvider(
            model=profile.embedding_profile,
            vectors_by_text={"recover worker": (1.0, 0.0, 0.0)},
        )
    )
    app.dependency_overrides[get_answer_model_client] = lambda: fake_model
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"question": "recover worker", "limit": 1},
        headers={"X-Zsper-Profile-Id": "work"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "work"
    assert body["question"] == "recover worker"
    assert body["answer"]["answer_confidence"] == 0.74
    assert body["answer"]["citations"][0]["document_id"] == document.id
    assert body["answer"]["citations"][0]["chunk_id"] == chunk.id
    assert body["answer"]["citations"][0]["citation_anchor_id"] == anchor.id
    assert body["answer"]["citations"][0]["display_range"] == anchor.display_range
    assert body["answer"]["citations"][0]["citation_confidence"] != (
        body["answer"]["answer_confidence"]
    )


def test_cli_brain_answer_prints_structured_json(
    tmp_path: Path,
    isolated_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from zsper.cli import app
    from zsper.rag.answer import AnswerCitation, AnswerResult

    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )

    def fake_answer_question_profile(profile: Profile, question: str) -> AnswerResult:
        assert profile.name == "work"
        assert question == "recover worker"
        return AnswerResult(
            profile_id=profile.name,
            question=question,
            text="Restart the worker.",
            answer_confidence=0.61,
            citations=(
                AnswerCitation(
                    document_id="doc-answer",
                    chunk_id="chunk-answer",
                    citation_anchor_id="anchor-answer",
                    source_path_or_url="/profiles/work/source.txt",
                    display_range="bytes 0-20",
                    text_preview="Restart the worker.",
                    citation_confidence=0.91,
                ),
            ),
            model=profile.model_profile,
        )

    monkeypatch.setattr(
        "zsper.brain.rag_commands.answer_question_profile",
        fake_answer_question_profile,
    )

    exit_code = app(["brain", "answer", "recover", "worker", "--profile", "work"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    body = json.loads(captured.out)
    assert body["answer_confidence"] == 0.61
    assert body["citations"][0]["citation_confidence"] == 0.91
    assert body["citations"][0]["citation_anchor_id"] == "anchor-answer"
