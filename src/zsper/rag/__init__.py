"""RAG document models, policy gates, and profile-scoped stores."""

from zsper.rag.chunking import (
    ChunkLocationMetadata,
    ChunkSourceLocation,
    ChunkingError,
    ChunkingResult,
    chunk_document,
)
from zsper.rag.citations import (
    CitationAnchorResult,
    CitationError,
    CitationSourceContext,
    generate_citation_anchors,
    inspect_citation_source,
)
from zsper.rag.models import (
    DOCUMENT_PARSERS,
    DOCUMENT_SOURCE_TYPES,
    CitationAnchor,
    Document,
    DocumentChunk,
    EmbeddingMetadata,
    RagModelError,
)
from zsper.rag.policy import HOSTED_RAG_ACTIONS, RagPolicyError, RagPolicyGate
from zsper.rag.store import (
    POSTGRES_RAG_SCHEMA_SQL,
    SQLITE_RAG_SCHEMA_SQL,
    ProfileRagStore,
    RagStoreError,
    replay_document_metadata,
)

__all__ = [
    "DOCUMENT_PARSERS",
    "DOCUMENT_SOURCE_TYPES",
    "HOSTED_RAG_ACTIONS",
    "POSTGRES_RAG_SCHEMA_SQL",
    "SQLITE_RAG_SCHEMA_SQL",
    "CitationAnchor",
    "CitationAnchorResult",
    "CitationError",
    "CitationSourceContext",
    "ChunkLocationMetadata",
    "ChunkSourceLocation",
    "ChunkingError",
    "ChunkingResult",
    "Document",
    "DocumentChunk",
    "EmbeddingMetadata",
    "ProfileRagStore",
    "RagModelError",
    "RagPolicyError",
    "RagPolicyGate",
    "RagStoreError",
    "chunk_document",
    "generate_citation_anchors",
    "inspect_citation_source",
    "replay_document_metadata",
]
