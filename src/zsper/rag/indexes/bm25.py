"""Profile-scoped SQLite BM25 index for exact RAG chunk retrieval."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from zsper.profiles import Profile
from zsper.rag.models import Document, DocumentChunk


BM25_SCHEMA_SQL: Final[str] = """
CREATE VIRTUAL TABLE IF NOT EXISTS bm25_chunks USING fts5(
  profile_id UNINDEXED,
  document_id UNINDEXED,
  chunk_id UNINDEXED,
  text,
  metadata,
  text_preview UNINDEXED,
  tokenize = 'unicode61'
);
"""

_QUERY_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9]+")
_TEXT_PREVIEW_CHARS: Final[int] = 240


class Bm25IndexError(ValueError):
    """Raised when a BM25 index operation is invalid."""


@dataclass(frozen=True)
class Bm25SearchResult:
    profile_id: str
    document_id: str
    chunk_id: str
    score: float
    text_preview: str


@dataclass(frozen=True)
class ProfileBm25Index:
    database_path: Path

    @classmethod
    def sqlite(cls, database_path: str | Path) -> "ProfileBm25Index":
        index = cls(Path(database_path).expanduser().resolve(strict=False))
        index.initialize()
        return index

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(BM25_SCHEMA_SQL)

    def index_chunks(
        self,
        profile: Profile,
        document: Document,
        chunks: Sequence[DocumentChunk],
        metadata_by_chunk_id: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        if document.profile_id != profile.name:
            raise Bm25IndexError(
                "document profile_id must match the profile used for indexing"
            )
        chunk_metadata = metadata_by_chunk_id or {}
        rows = [
            (
                profile.name,
                document.id,
                chunk.id,
                chunk.text,
                _metadata_text(
                    document=document,
                    chunk=chunk,
                    chunk_metadata=chunk_metadata.get(chunk.id, {}),
                ),
                _text_preview(chunk.text),
            )
            for chunk in chunks
        ]
        for chunk in chunks:
            if chunk.document_id != document.id:
                raise Bm25IndexError(
                    "chunk document_id must match the document used for indexing"
                )

        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM bm25_chunks
                WHERE profile_id = ? AND document_id = ?
                """,
                (profile.name, document.id),
            )
            conn.executemany(
                """
                INSERT INTO bm25_chunks (
                  profile_id,
                  document_id,
                  chunk_id,
                  text,
                  metadata,
                  text_preview
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def search(
        self,
        profile: Profile,
        query: str,
        limit: int = 10,
    ) -> list[Bm25SearchResult]:
        if limit <= 0:
            return []
        match_query = _match_query(query)
        if not match_query:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  profile_id,
                  document_id,
                  chunk_id,
                  bm25(bm25_chunks) AS rank,
                  text_preview
                FROM bm25_chunks
                WHERE profile_id = ? AND bm25_chunks MATCH ?
                ORDER BY rank ASC, document_id, chunk_id
                LIMIT ?
                """,
                (profile.name, match_query, limit),
            ).fetchall()
        return [
            Bm25SearchResult(
                profile_id=row["profile_id"],
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                score=max(0.0, -float(row["rank"])),
                text_preview=row["text_preview"],
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn


def _match_query(query: str) -> str:
    terms = tuple(dict.fromkeys(_QUERY_TOKEN_RE.findall(query.lower())))
    return " AND ".join(f'"{term}"' for term in terms)


def _metadata_text(
    *,
    document: Document,
    chunk: DocumentChunk,
    chunk_metadata: Mapping[str, Any],
) -> str:
    metadata = {
        "document": {
            "id": document.id,
            "profile_id": document.profile_id,
            "source_type": document.source_type,
            "raw_asset_path": document.raw_asset_path,
            "parsed_representation_path": document.parsed_representation_path,
            "title": document.title,
            "metadata": document.metadata,
            "content_hash": document.content_hash,
            "parser": document.parser,
        },
        "chunk": {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "citation_anchor_id": chunk.citation_anchor_id,
            "byte_start": chunk.byte_start,
            "byte_end": chunk.byte_end,
            "embedding_model": chunk.embedding_model,
            "embedding_vector_id": chunk.embedding_vector_id,
            "metadata": dict(chunk_metadata),
        },
    }
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"), default=str)


def _text_preview(text: str) -> str:
    preview = " ".join(text.split())
    if len(preview) <= _TEXT_PREVIEW_CHARS:
        return preview
    return preview[: _TEXT_PREVIEW_CHARS - 3].rstrip() + "..."
