"""Handlers for `zsper brain` RAG commands."""

from __future__ import annotations

import json
import os
import sys
from argparse import Namespace
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from zsper.config.user import UserConfigError, profile_ref_or_default
from zsper.profiles import Profile, ProfileError, resolve_profile
from zsper.rag import (
    AnswerError,
    ChunkingError,
    CitationError,
    HybridSearchEngine,
    HybridSearchError,
    ProfileRagStore,
    RagPolicyError,
    RagStoreError,
    answer_question,
    chunk_document,
    generate_citation_anchors,
)
from zsper.rag.assets import RawAssetCaptureError, capture_local_asset
from zsper.rag.embeddings import EmbeddingError, embed_chunks, provider_for_profile
from zsper.rag.indexes import (
    Bm25IndexError,
    ProfileBm25Index,
    ProfileVectorIndex,
    VectorIndexError,
)
from zsper.rag.parsers import (
    DoclingParserFailure,
    ParserSelectionError,
    ParserRoute,
    TextParserError,
    parse_docling_document,
    parse_text_document,
    select_parser,
)
from zsper.rag.web_capture import WebCaptureError, capture_webpage_asset
from zsper.security.network_policy import LOCALHOST_NAMES


LOCAL_POSTGRES_HOSTS = LOCALHOST_NAMES | {"postgres"}


@dataclass(frozen=True)
class RagCommandComponents:
    store: ProfileRagStore
    bm25_index: ProfileBm25Index
    vector_index: ProfileVectorIndex


@dataclass(frozen=True)
class RagIngestResult:
    document_id: str
    chunk_count: int
    source_path_or_url: str
    rag_database_path: Path | None
    bm25_database_path: Path
    vector_database_path: Path | None


class RagCommandError(ValueError):
    """Raised when a CLI RAG command cannot complete."""


def ingest(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1

    if not namespace.path_or_url:
        print("path-or-url is required for brain ingest", file=sys.stderr)
        return 2

    try:
        result = ingest_source(profile, namespace.path_or_url)
    except _COMMAND_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        f"ingested document {result.document_id}\t"
        f"{result.chunk_count} chunks\t{result.source_path_or_url}"
    )
    return 0


def search(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1

    query = _query_from_namespace(namespace, command="brain search")
    if query is None:
        return 2

    try:
        results = search_profile(profile, query)
    except _COMMAND_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for result in results:
        components = (
            f"bm25={result.score_components['bm25']:.6g},"
            f"dense={result.score_components['dense']:.6g}"
        )
        print(
            f"{result.score:.6g}\t{result.document_id}\t{result.chunk_id}\t"
            f"{result.citation_anchor_id}\t{result.source_path_or_url}\t"
            f"{components}\t{result.text_preview}"
        )
    return 0


def answer(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1

    question = _query_from_namespace(namespace, command="brain answer")
    if question is None:
        return 2

    try:
        answer_result = answer_question_profile(profile, question)
    except _COMMAND_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(answer_result.to_dict(), indent=2, sort_keys=True))
    return 0


def ingest_source(profile: Profile, source: str | Path) -> RagIngestResult:
    route = select_parser(source, profile=profile, user_triggered=True)
    components = components_for_profile(profile)
    document = _capture_document(profile, components.store, route)
    _parse_document(document)

    chunking_result = chunk_document(profile, components.store, document)
    generate_citation_anchors(profile, components.store, document, chunking_result)
    embedding_result = embed_chunks(
        profile,
        components.store,
        document.id,
        provider=provider_for_profile(profile),
    )

    chunks = tuple(components.store.list_chunks(profile, document.id))
    vectors_by_chunk_id = dict(
        zip(
            (record.chunk_id for record in embedding_result.records),
            embedding_result.vectors,
            strict=True,
        )
    )
    components.bm25_index.index_chunks(profile, document, chunks)
    components.vector_index.index_chunks(
        profile,
        document,
        chunks,
        vectors_by_chunk_id=vectors_by_chunk_id,
    )
    return RagIngestResult(
        document_id=document.id,
        chunk_count=len(chunks),
        source_path_or_url=_source_path_or_url(document),
        rag_database_path=components.store.database_path,
        bm25_database_path=components.bm25_index.database_path,
        vector_database_path=components.vector_index.database_path,
    )


def search_profile(profile: Profile, query: str):
    engine, _store = search_components_for_profile(profile)
    return engine.search(profile, query)


def answer_question_profile(profile: Profile, question: str):
    engine, store = search_components_for_profile(profile)
    results = engine.search(profile, question)
    return answer_question(profile, store, question, results)


def search_components_for_profile(
    profile: Profile,
) -> tuple[HybridSearchEngine, ProfileRagStore]:
    components = components_for_profile(profile)
    engine = HybridSearchEngine(
        store=components.store,
        bm25_index=components.bm25_index,
        vector_index=components.vector_index,
        query_embedding_provider=provider_for_profile(profile),
    )
    return engine, components.store


def components_for_profile(profile: Profile) -> RagCommandComponents:
    index_root = Path(profile.root) / "brain" / "indexes"
    postgres_dsn = os.environ.get("POSTGRES_DSN")
    rag_sqlite_path = os.environ.get("ZSPER_RAG_SQLITE_PATH")
    vector_sqlite_path = os.environ.get("ZSPER_VECTOR_SQLITE_PATH")
    if postgres_dsn:
        _require_local_postgres_dsn(postgres_dsn)

    if rag_sqlite_path or profile.storage_backend == "sqlite-local" or not postgres_dsn:
        store = ProfileRagStore.sqlite(rag_sqlite_path or index_root / "rag.sqlite")
    else:
        store = ProfileRagStore.postgres_dsn(postgres_dsn)

    bm25_index = ProfileBm25Index.sqlite(
        os.environ.get("ZSPER_BM25_SQLITE_PATH") or index_root / "bm25.sqlite"
    )

    if (
        vector_sqlite_path
        or profile.storage_backend == "sqlite-local"
        or not postgres_dsn
    ):
        vector_index = ProfileVectorIndex.sqlite(
            vector_sqlite_path or index_root / "vectors.sqlite"
        )
    else:
        vector_index = ProfileVectorIndex.postgres_dsn(postgres_dsn)

    return RagCommandComponents(
        store=store,
        bm25_index=bm25_index,
        vector_index=vector_index,
    )


def _require_local_postgres_dsn(dsn: str) -> None:
    parsed = urlparse(dsn)
    if not parsed.scheme.startswith("postgres"):
        raise RagCommandError("Postgres DSN must use a postgres scheme")
    for host in _postgres_dsn_hosts(parsed):
        if host not in LOCAL_POSTGRES_HOSTS:
            raise RagCommandError("Postgres DSN must point at a local service")


def _postgres_dsn_hosts(parsed) -> tuple[str, ...]:
    hosts: list[str] = []
    if parsed.hostname is not None:
        hosts.append(parsed.hostname)
    params = parse_qs(parsed.query, keep_blank_values=False)
    for key in ("host", "hostaddr"):
        for value in params.get(key, ()):
            for host in value.split(","):
                normalized = host.strip()
                if normalized:
                    hosts.append(normalized)
    return tuple(hosts)


def handler(command: str):
    return {
        "ingest": ingest,
        "search": search,
        "answer": answer,
    }[command]


def _resolve(namespace: Namespace) -> Profile | None:
    try:
        return resolve_profile(profile_ref_or_default(namespace.profile))
    except (ProfileError, UserConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return None


def _query_from_namespace(namespace: Namespace, *, command: str) -> str | None:
    query = " ".join(namespace.query).strip()
    if not query:
        print(f"query is required for {command}", file=sys.stderr)
        return None
    return query


def _capture_document(
    profile: Profile,
    store: ProfileRagStore,
    route: ParserRoute,
):
    if route.source_type == "url":
        return capture_webpage_asset(
            profile,
            store,
            route.source,
            user_triggered=True,
        )
    if route.source_type == "repo":
        raise RagCommandError("repo ingestion is not implemented for brain ingest")
    return capture_local_asset(profile, store, route.source)


def _parse_document(document) -> None:
    if document.parser == "text":
        parse_text_document(document)
        return
    if document.parser == "docling":
        parsed = parse_docling_document(document)
        if isinstance(parsed, DoclingParserFailure):
            raise RagCommandError(parsed.reason)
        return
    if document.parser == "web-capture":
        _parse_web_capture_document(document)
        return
    raise RagCommandError(f"unsupported parser route for brain ingest: {document.parser}")


def _parse_web_capture_document(document) -> None:
    raw_path = Path(document.raw_asset_path)
    parsed_path = Path(document.parsed_representation_path)
    try:
        raw_bytes = raw_path.read_bytes()
    except OSError as exc:
        raise RagCommandError(
            f"web capture parser could not read raw asset for document {document.id}: "
            f"{raw_path}"
        ) from exc
    text = _web_capture_text(raw_bytes, media_type=document.metadata.get("media_type"))
    if not text.strip():
        raise RagCommandError(f"web capture produced no text for document {document.id}")
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text(text, encoding="utf-8")


def _web_capture_text(raw_bytes: bytes, *, media_type: Any) -> str:
    decoded = raw_bytes.decode("utf-8", errors="replace")
    if isinstance(media_type, str) and media_type.split(";", 1)[0].strip().lower() in {
        "text/html",
        "application/xhtml+xml",
    }:
        parser = _HTMLTextParser()
        parser.feed(decoded)
        text = "\n".join(parser.parts)
        lines = (part.strip() for part in text.splitlines())
        return "\n".join(line for line in lines if line)
    return decoded


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        stripped = " ".join(data.split())
        if stripped:
            self.parts.append(stripped)


def _source_path_or_url(document) -> str:
    for key in ("original_url", "final_url", "original_path"):
        value = document.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return document.raw_asset_path


_COMMAND_ERRORS = (
    AnswerError,
    Bm25IndexError,
    ChunkingError,
    CitationError,
    EmbeddingError,
    HybridSearchError,
    ParserSelectionError,
    RagCommandError,
    RagPolicyError,
    RagStoreError,
    RawAssetCaptureError,
    TextParserError,
    VectorIndexError,
    WebCaptureError,
)
