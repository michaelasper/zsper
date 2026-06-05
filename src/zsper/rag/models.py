"""RAG document models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DOCUMENT_SOURCE_TYPES = frozenset({"file", "url", "repo", "note", "agent_artifact"})
DOCUMENT_PARSERS = frozenset({"text", "docling", "web-capture", "repo"})


class RagModelError(ValueError):
    """Raised when a RAG model is invalid."""


def _require_non_empty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RagModelError(f"{name} must be a non-empty string")


def _require_optional_non_empty(name: str, value: str | None) -> None:
    if value is not None:
        _require_non_empty(name, value)


def _require_non_negative_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RagModelError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class EmbeddingMetadata:
    model: str | None
    vector_id: str | None

    def __post_init__(self) -> None:
        _require_optional_non_empty("embedding model", self.model)
        _require_optional_non_empty("embedding vector_id", self.vector_id)

    def to_dict(self) -> dict[str, str | None]:
        return {"model": self.model, "vector_id": self.vector_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmbeddingMetadata":
        return cls(
            model=data.get("model"),
            vector_id=data.get("vector_id"),
        )


@dataclass(frozen=True)
class Document:
    id: str
    profile_id: str
    source_type: str
    raw_asset_path: str
    parsed_representation_path: str
    title: str
    metadata: dict[str, Any]
    content_hash: str
    parser: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "id",
            "profile_id",
            "raw_asset_path",
            "parsed_representation_path",
            "title",
            "content_hash",
            "created_at",
            "updated_at",
        ):
            _require_non_empty(field_name, getattr(self, field_name))
        if self.source_type not in DOCUMENT_SOURCE_TYPES:
            raise RagModelError(f"invalid document source_type: {self.source_type}")
        if self.parser not in DOCUMENT_PARSERS:
            raise RagModelError(f"invalid document parser: {self.parser}")
        if not isinstance(self.metadata, dict):
            raise RagModelError("document metadata must be a dictionary")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "source_type": self.source_type,
            "raw_asset_path": self.raw_asset_path,
            "parsed_representation_path": self.parsed_representation_path,
            "title": self.title,
            "metadata": dict(self.metadata),
            "content_hash": self.content_hash,
            "parser": self.parser,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        return cls(
            id=data["id"],
            profile_id=data["profile_id"],
            source_type=data["source_type"],
            raw_asset_path=data["raw_asset_path"],
            parsed_representation_path=data["parsed_representation_path"],
            title=data["title"],
            metadata=data["metadata"],
            content_hash=data["content_hash"],
            parser=data["parser"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    document_id: str
    chunk_index: int
    text: str
    citation_anchor_id: str
    token_estimate: int
    byte_start: int | None
    byte_end: int | None
    embedding_model: str | None
    embedding_vector_id: str | None

    def __post_init__(self) -> None:
        for field_name in ("id", "document_id", "text", "citation_anchor_id"):
            _require_non_empty(field_name, getattr(self, field_name))
        _require_non_negative_int("chunk_index", self.chunk_index)
        _require_non_negative_int("token_estimate", self.token_estimate)
        if self.byte_start is not None:
            _require_non_negative_int("byte_start", self.byte_start)
        if self.byte_end is not None:
            _require_non_negative_int("byte_end", self.byte_end)
        if (
            self.byte_start is not None
            and self.byte_end is not None
            and self.byte_end < self.byte_start
        ):
            raise RagModelError("byte_end must be greater than or equal to byte_start")
        _require_optional_non_empty("embedding_model", self.embedding_model)
        _require_optional_non_empty("embedding_vector_id", self.embedding_vector_id)

    @property
    def embedding(self) -> EmbeddingMetadata:
        return EmbeddingMetadata(
            model=self.embedding_model,
            vector_id=self.embedding_vector_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "citation_anchor_id": self.citation_anchor_id,
            "token_estimate": self.token_estimate,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "embedding_model": self.embedding_model,
            "embedding_vector_id": self.embedding_vector_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentChunk":
        return cls(
            id=data["id"],
            document_id=data["document_id"],
            chunk_index=data["chunk_index"],
            text=data["text"],
            citation_anchor_id=data["citation_anchor_id"],
            token_estimate=data["token_estimate"],
            byte_start=data["byte_start"],
            byte_end=data["byte_end"],
            embedding_model=data["embedding_model"],
            embedding_vector_id=data["embedding_vector_id"],
        )


@dataclass(frozen=True)
class CitationAnchor:
    id: str
    document_id: str
    chunk_id: str
    label: str
    source_path_or_url: str
    display_range: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "id",
            "document_id",
            "chunk_id",
            "label",
            "source_path_or_url",
        ):
            _require_non_empty(field_name, getattr(self, field_name))
        _require_optional_non_empty("display_range", self.display_range)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "label": self.label,
            "source_path_or_url": self.source_path_or_url,
            "display_range": self.display_range,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CitationAnchor":
        return cls(
            id=data["id"],
            document_id=data["document_id"],
            chunk_id=data["chunk_id"],
            label=data["label"],
            source_path_or_url=data["source_path_or_url"],
            display_range=data["display_range"],
        )
