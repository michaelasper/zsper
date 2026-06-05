"""Setup-time RAG indexing helpers for local profile bootstrap flows."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from zsper.profiles import Profile
from zsper.rag.assets import capture_local_asset
from zsper.rag.chunking import chunk_document
from zsper.rag.citations import generate_citation_anchors
from zsper.rag.embeddings import embed_chunks, provider_for_profile
from zsper.rag.indexes import ProfileBm25Index, ProfileVectorIndex
from zsper.rag.parsers import parse_text_document
from zsper.rag.policy import RagPolicyGate
from zsper.rag.store import ProfileRagStore


@dataclass(frozen=True)
class SetupIndexResult:
    document_id: str
    chunk_count: int
    rag_database_path: Path
    bm25_database_path: Path
    vector_database_path: Path


def index_local_text_file(profile: Profile, source: str | Path) -> SetupIndexResult:
    """Index a local text file into the profile-local hybrid RAG stores."""

    if profile.mode != "air-offline":
        raise ValueError("setup RAG indexing requires an air-offline profile")

    RagPolicyGate(profile).require_ingest(source, user_triggered=True)
    index_root = Path(profile.root) / "brain" / "indexes"
    store = ProfileRagStore.sqlite(index_root / "rag.sqlite")
    bm25_index = ProfileBm25Index.sqlite(index_root / "bm25.sqlite")
    vector_index = ProfileVectorIndex.sqlite(index_root / "vectors.sqlite")

    document = capture_local_asset(profile, store, source)
    if document.parser != "text":
        raise ValueError("setup RAG indexing accepts text-routed files only")

    parse_text_document(document)
    chunking_result = chunk_document(profile, store, document)
    generate_citation_anchors(profile, store, document, chunking_result)
    embedding_result = embed_chunks(
        profile,
        store,
        document.id,
        provider=provider_for_profile(profile),
    )

    chunks = tuple(store.list_chunks(profile, document.id))
    bm25_index.index_chunks(profile, document, chunks)
    vector_index.index_chunks(
        profile,
        document,
        chunks,
        vectors_by_chunk_id=dict(
            zip(
                (record.chunk_id for record in embedding_result.records),
                embedding_result.vectors,
                strict=True,
            )
        ),
    )
    return SetupIndexResult(
        document_id=document.id,
        chunk_count=len(chunks),
        rag_database_path=index_root / "rag.sqlite",
        bm25_database_path=index_root / "bm25.sqlite",
        vector_database_path=index_root / "vectors.sqlite",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Index a local setup file into profile-local hybrid RAG stores."
    )
    parser.add_argument("--profile-json", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args(argv)

    try:
        profile_data = json.loads(Path(args.profile_json).read_text(encoding="utf-8"))
        result = index_local_text_file(Profile.from_dict(profile_data), args.source)
    except Exception as exc:
        print(f"setup RAG indexing failed: {exc}", file=sys.stderr)
        return 1

    print(f"indexed RAG document {result.document_id}\t{result.chunk_count} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
