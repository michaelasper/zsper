from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from zsper.brain import rag_commands
from zsper.profiles import Profile, initialize_profile
from zsper.rag import RagPolicyError, RagPolicyGate
from zsper.rag.models import CitationAnchor, Document, DocumentChunk
from zsper.rag.parsers.docling import ParsedDoclingDocument, parse_docling_document
from zsper.rag.web_capture import WebCaptureResult, capture_webpage_asset


FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
SAMPLE_MD = FIXTURES_ROOT / "documents" / "sample.md"
SAMPLE_PDF = FIXTURES_ROOT / "documents" / "sample.pdf"
REPO_DOCS_ROOT = FIXTURES_ROOT / "repo-docs"
WEB_URL = "https://example.com/zsper/rag-acceptance"


@dataclass(frozen=True)
class _AcceptancePatches:
    docling_converter: "_FakeDoclingConverter"
    web_capture_calls: list[str]
    model_prompts: list[dict[str, Any]]


@dataclass(frozen=True)
class _FakeDoclingItem:
    text: str
    page: int | None = None
    heading: str | None = None
    section: str | None = None
    metadata: dict[str, Any] | None = None


class _FakeDoclingDocument:
    def __init__(self, items: Sequence[_FakeDoclingItem]) -> None:
        self.items = tuple(items)

    def export_to_markdown(self) -> str:
        return "\n\n".join(item.text for item in self.items)


@dataclass(frozen=True)
class _FakeConversionResult:
    document: _FakeDoclingDocument


class _FakeDoclingConverter:
    def __init__(self) -> None:
        self.sources: list[str] = []
        self.document = _FakeDoclingDocument(
            [
                _FakeDoclingItem(
                    text="# Acceptance PDF",
                    page=1,
                    heading="Acceptance PDF",
                    section="Overview",
                    metadata={"kind": "heading"},
                ),
                _FakeDoclingItem(
                    text=(
                        "The semantic acceptance anchor explains citation "
                        "anchors for grounded answers and source inspection."
                    ),
                    page=2,
                    heading="Acceptance PDF",
                    section="Grounding",
                    metadata={"kind": "paragraph"},
                ),
            ]
        )

    def convert(self, source: str) -> _FakeConversionResult:
        self.sources.append(source)
        return _FakeConversionResult(self.document)


@dataclass(frozen=True)
class _AcceptanceEmbeddingProvider:
    model: str

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(_embedding_vector(text) for text in texts)


def _embedding_vector(text: str) -> tuple[float, float, float]:
    normalized = text.lower()
    if "conceptual bridge lookup" in normalized:
        return (1.0, 0.0, 0.0)
    if "semantic acceptance anchor" in normalized:
        return (1.0, 0.0, 0.0)
    if "rag acceptance exact token" in normalized:
        return (0.0, 1.0, 0.0)
    if "web capture acceptance source" in normalized:
        return (0.0, 0.0, 1.0)
    if "offline file only retrieval" in normalized:
        return (0.25, 0.25, 0.25)
    return (0.1, 0.2, 0.3)


def _install_acceptance_patches(
    monkeypatch: pytest.MonkeyPatch,
) -> _AcceptancePatches:
    docling_converter = _FakeDoclingConverter()
    web_capture_calls: list[str] = []
    model_prompts: list[dict[str, Any]] = []

    def fake_provider_for_profile(profile: Profile) -> _AcceptanceEmbeddingProvider:
        return _AcceptanceEmbeddingProvider(profile.embedding_profile)

    def fake_parse_docling_document(document: Document) -> ParsedDoclingDocument:
        parsed = parse_docling_document(document, converter=docling_converter)
        assert isinstance(parsed, ParsedDoclingDocument)
        return parsed

    def fake_fetcher(target_url: str) -> WebCaptureResult:
        return WebCaptureResult(
            content=(
                "<html><head><title>Web RAG Acceptance</title></head>"
                "<body><main>Web capture acceptance source text is parsed "
                "from mocked HTML without live network access.</main></body></html>"
            ),
            final_url=target_url,
            media_type="text/html; charset=utf-8",
            extraction_status="extracted",
        )

    def fake_capture_webpage_asset(
        profile: Profile,
        store: Any,
        url: str,
        *,
        user_triggered: bool = False,
        **kwargs: Any,
    ) -> Document:
        web_capture_calls.append(url)
        return capture_webpage_asset(
            profile,
            store,
            url,
            fetcher=fake_fetcher,
            user_triggered=user_triggered,
            **kwargs,
        )

    def fake_create_chat_completion(
        self: object,
        *,
        url: str,
        payload: Mapping[str, object],
        timeout: float,
    ) -> Mapping[str, object]:
        del self, timeout
        assert url == "http://127.0.0.1:9127/v1/chat/completions"
        messages = payload["messages"]
        assert isinstance(messages, list)
        user_message = messages[1]
        assert isinstance(user_message, dict)
        prompt = json.loads(str(user_message["content"]))
        assert isinstance(prompt, dict)
        assert prompt["question"] == "conceptual bridge lookup"
        assert prompt["context"]
        model_prompts.append(prompt)
        cited_anchor_id = prompt["context"][0]["citation_anchor_id"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": (
                                    "The semantic acceptance anchor explains "
                                    "citation anchors for grounded answers."
                                ),
                                "answer_confidence": 0.91,
                                "citation_anchor_ids": [cited_anchor_id],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "zsper.brain.rag_commands.provider_for_profile",
        fake_provider_for_profile,
    )
    monkeypatch.setattr(
        "zsper.brain.rag_commands.parse_docling_document",
        fake_parse_docling_document,
    )
    monkeypatch.setattr(
        "zsper.brain.rag_commands.capture_webpage_asset",
        fake_capture_webpage_asset,
    )
    monkeypatch.setattr(
        "zsper.rag.answer.OpenAICompatibleAnswerModelClient.create_chat_completion",
        fake_create_chat_completion,
    )
    return _AcceptancePatches(
        docling_converter=docling_converter,
        web_capture_calls=web_capture_calls,
        model_prompts=model_prompts,
    )


def _initialize_profile(
    *,
    mode: str,
    root: Path,
    registry_path: Path,
    network_policy: str | None = None,
) -> Profile:
    return initialize_profile(
        mode=mode,
        root=root,
        registry_path=registry_path,
        network_policy=network_policy,
    )


def _clear_rag_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("ZSPER_RAG_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_BM25_SQLITE_PATH", raising=False)
    monkeypatch.delenv("ZSPER_VECTOR_SQLITE_PATH", raising=False)


def _use_sqlite_rag_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ZSPER_RAG_SQLITE_PATH", str(tmp_path / "rag.sqlite"))
    monkeypatch.setenv("ZSPER_BM25_SQLITE_PATH", str(tmp_path / "bm25.sqlite"))
    monkeypatch.setenv("ZSPER_VECTOR_SQLITE_PATH", str(tmp_path / "vectors.sqlite"))


def _stored_document(
    profile: Profile,
    document_id: str,
) -> tuple[Document, list[DocumentChunk], list[CitationAnchor]]:
    components = rag_commands.components_for_profile(profile)
    document = components.store.get_document(profile, document_id)
    assert document is not None
    chunks = components.store.list_chunks(profile, document.id)
    anchors = components.store.list_citation_anchors(profile, document.id)
    return document, chunks, anchors


def _assert_ingested_document(profile: Profile, document_id: str) -> Document:
    document, chunks, anchors = _stored_document(profile, document_id)

    assert Path(document.raw_asset_path).is_file()
    assert Path(document.parsed_representation_path).is_file()
    assert chunks
    assert len(anchors) == len(chunks)
    assert {anchor.chunk_id for anchor in anchors} == {chunk.id for chunk in chunks}
    assert all(
        anchor.id == chunk.citation_anchor_id
        for anchor in anchors
        for chunk in chunks
        if chunk.id == anchor.chunk_id
    )
    assert all(chunk.embedding_model == profile.embedding_profile for chunk in chunks)
    assert all(chunk.embedding_vector_id for chunk in chunks)
    return document


def _anchor_for_result(
    profile: Profile,
    document_id: str,
    anchor_id: str,
) -> CitationAnchor:
    document, _chunks, anchors = _stored_document(profile, document_id)
    del document
    for anchor in anchors:
        if anchor.id == anchor_id:
            return anchor
    raise AssertionError(f"missing citation anchor {anchor_id}")


def test_rag_acceptance_ingests_searches_and_answers_with_exact_citations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _clear_rag_env(monkeypatch)
    patches = _install_acceptance_patches(monkeypatch)
    profile = _initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    _use_sqlite_rag_env(monkeypatch, tmp_path)

    markdown_result = rag_commands.ingest_source(profile, SAMPLE_MD)
    pdf_result = rag_commands.ingest_source(profile, SAMPLE_PDF)
    web_result = rag_commands.ingest_source(profile, WEB_URL)
    repo_docs_result = rag_commands.ingest_source(profile, REPO_DOCS_ROOT)

    markdown_document = _assert_ingested_document(profile, markdown_result.document_id)
    pdf_document = _assert_ingested_document(profile, pdf_result.document_id)
    web_document = _assert_ingested_document(profile, web_result.document_id)
    repo_document = _assert_ingested_document(profile, repo_docs_result.document_id)
    assert markdown_document.parser == "text"
    assert pdf_document.parser == "docling"
    assert web_document.parser == "web-capture"
    assert repo_document.parser == "repo"
    assert repo_document.metadata["original_path"] == str(REPO_DOCS_ROOT.resolve())
    assert patches.docling_converter.sources == [pdf_document.raw_asset_path]
    assert patches.web_capture_calls == [WEB_URL]

    exact_results = rag_commands.search_profile(profile, "rag acceptance exact token")
    assert exact_results
    assert exact_results[0].document_id == markdown_document.id
    assert exact_results[0].source_path_or_url == str(SAMPLE_MD.resolve())
    assert exact_results[0].score_components["bm25"] > 0.0
    assert "rag acceptance exact token" in exact_results[0].text_preview

    dense_results = rag_commands.search_profile(profile, "conceptual bridge lookup")
    assert dense_results
    assert dense_results[0].document_id == pdf_document.id
    assert dense_results[0].source_path_or_url == str(SAMPLE_PDF.resolve())
    assert dense_results[0].score_components["bm25"] == 0.0
    assert dense_results[0].score_components["dense"] > 0.99

    answer = rag_commands.answer_question_profile(profile, "conceptual bridge lookup")
    assert answer.text == (
        "The semantic acceptance anchor explains citation anchors for grounded answers."
    )
    assert answer.answer_confidence == 0.91
    assert len(answer.citations) == 1
    assert patches.model_prompts
    cited_context = patches.model_prompts[0]["context"][0]
    citation = answer.citations[0]
    stored_anchor = _anchor_for_result(
        profile,
        str(cited_context["document_id"]),
        str(cited_context["citation_anchor_id"]),
    )
    assert citation.document_id == stored_anchor.document_id
    assert citation.chunk_id == stored_anchor.chunk_id
    assert citation.citation_anchor_id == stored_anchor.id
    assert citation.source_path_or_url == stored_anchor.source_path_or_url
    assert citation.display_range == stored_anchor.display_range
    assert citation.text_preview == cited_context["text_preview"]
    assert answer.to_dict()["citations"] == [citation.to_dict()]


def test_offline_state_acceptance_is_file_only_and_blocks_hosted_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _clear_rag_env(monkeypatch)
    patches = _install_acceptance_patches(monkeypatch)
    profile = _initialize_profile(
        mode="air",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
        network_policy="offline",
    )

    result = rag_commands.ingest_source(profile, REPO_DOCS_ROOT)
    document = _assert_ingested_document(profile, result.document_id)
    assert document.parser == "repo"
    assert document.metadata["original_path"] == str(REPO_DOCS_ROOT.resolve())

    results = rag_commands.search_profile(profile, "offline file only retrieval")
    assert results
    assert results[0].document_id == document.id
    assert results[0].score_components["bm25"] > 0.0
    assert "offline file only retrieval" in results[0].text_preview

    with pytest.raises(RagPolicyError, match="offline policy blocks url-ingest"):
        rag_commands.ingest_source(profile, WEB_URL)
    assert patches.web_capture_calls == []

    gate = RagPolicyGate(profile)
    with pytest.raises(RagPolicyError, match="offline policy blocks hosted-model-api"):
        gate.require_hosted_dependency(
            "https://api.openai.com/v1/chat/completions",
            action="hosted-model-api",
        )
    with pytest.raises(
        RagPolicyError,
        match="offline policy blocks hosted-extraction-api",
    ):
        gate.require_hosted_dependency(
            "https://api.firecrawl.dev/v1/scrape",
            action="hosted-extraction-api",
        )
