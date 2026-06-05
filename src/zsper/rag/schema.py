"""Shared SQL schema constants for profile-scoped RAG storage."""

from __future__ import annotations


SQLITE_RAG_SCHEMA_SQL = """-- Zsper RAG SQLite-compatible logical schema.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
  profile_id TEXT NOT NULL,
  id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  raw_asset_path TEXT NOT NULL,
  parsed_representation_path TEXT NOT NULL,
  title TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  parser TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (profile_id, id)
);

CREATE TABLE IF NOT EXISTS document_chunks (
  profile_id TEXT NOT NULL,
  id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  citation_anchor_id TEXT NOT NULL,
  token_estimate INTEGER NOT NULL,
  byte_start INTEGER,
  byte_end INTEGER,
  embedding_model TEXT,
  embedding_vector_id TEXT,
  PRIMARY KEY (profile_id, id),
  UNIQUE (profile_id, document_id, chunk_index),
  FOREIGN KEY (profile_id, document_id) REFERENCES documents (profile_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS citation_anchors (
  profile_id TEXT NOT NULL,
  id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  label TEXT NOT NULL,
  source_path_or_url TEXT NOT NULL,
  display_range TEXT,
  PRIMARY KEY (profile_id, id),
  FOREIGN KEY (profile_id, document_id) REFERENCES documents (profile_id, id) ON DELETE CASCADE,
  FOREIGN KEY (profile_id, chunk_id) REFERENCES document_chunks (profile_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_profile_updated_at
  ON documents (profile_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_document_chunks_document
  ON document_chunks (profile_id, document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_rag_citation_anchors_document
  ON citation_anchors (profile_id, document_id);
"""


POSTGRES_RAG_SCHEMA_SQL = """-- Zsper RAG Postgres + pgvector logical schema.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  profile_id TEXT NOT NULL,
  id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  raw_asset_path TEXT NOT NULL,
  parsed_representation_path TEXT NOT NULL,
  title TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  content_hash TEXT NOT NULL,
  parser TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (profile_id, id)
);

CREATE TABLE IF NOT EXISTS document_chunks (
  profile_id TEXT NOT NULL,
  id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  citation_anchor_id TEXT NOT NULL,
  token_estimate INTEGER NOT NULL,
  byte_start INTEGER,
  byte_end INTEGER,
  embedding_model TEXT,
  embedding_vector_id TEXT,
  embedding vector(384),
  PRIMARY KEY (profile_id, id),
  UNIQUE (profile_id, document_id, chunk_index),
  FOREIGN KEY (profile_id, document_id) REFERENCES documents (profile_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS citation_anchors (
  profile_id TEXT NOT NULL,
  id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  label TEXT NOT NULL,
  source_path_or_url TEXT NOT NULL,
  display_range TEXT,
  PRIMARY KEY (profile_id, id),
  FOREIGN KEY (profile_id, document_id) REFERENCES documents (profile_id, id) ON DELETE CASCADE,
  FOREIGN KEY (profile_id, chunk_id) REFERENCES document_chunks (profile_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_profile_updated_at
  ON documents (profile_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_document_chunks_document
  ON document_chunks (profile_id, document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_rag_document_chunks_embedding
  ON document_chunks USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rag_citation_anchors_document
  ON citation_anchors (profile_id, document_id);
"""
