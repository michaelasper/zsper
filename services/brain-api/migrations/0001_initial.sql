-- Zsper Brain canonical Postgres schema.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS profile_metadata (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  mode TEXT NOT NULL,
  root TEXT NOT NULL,
  database_name TEXT NOT NULL,
  storage_backend TEXT NOT NULL,
  network_policy TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id),
  UNIQUE (profile_id, profile_name),
  UNIQUE (profile_name)
);

CREATE INDEX IF NOT EXISTS idx_profile_metadata_profile_name
  ON profile_metadata (profile_name);

-- Zsper RAG Postgres + pgvector logical schema.
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

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunk_vectors (
  profile_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_vector_id TEXT NOT NULL,
  embedding vector(384) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, document_id, chunk_id, embedding_model),
  UNIQUE (profile_id, embedding_vector_id)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunk_vectors_profile_model
  ON rag_chunk_vectors (profile_id, embedding_model);
CREATE INDEX IF NOT EXISTS idx_rag_chunk_vectors_embedding
  ON rag_chunk_vectors USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS notes (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  note_id UUID NOT NULL DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  tags TEXT[] NOT NULL DEFAULT '{}',
  source_document_id TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, note_id),
  UNIQUE (note_id),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE,
  FOREIGN KEY (profile_id, source_document_id) REFERENCES documents (profile_id, id) ON DELETE SET NULL (source_document_id)
);

CREATE TABLE IF NOT EXISTS tasks (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  task_id UUID NOT NULL DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  priority TEXT NOT NULL DEFAULT 'normal',
  due_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(status, ''))
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, task_id),
  UNIQUE (task_id),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_events (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  memory_event_id UUID NOT NULL DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  content TEXT NOT NULL,
  importance INTEGER NOT NULL DEFAULT 0,
  embedding vector(384),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(event_type, '') || ' ' || coalesce(content, ''))
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, memory_event_id),
  UNIQUE (memory_event_id),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS research_records (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  research_record_id UUID NOT NULL DEFAULT gen_random_uuid(),
  query TEXT NOT NULL,
  source_uri TEXT,
  title TEXT,
  summary TEXT NOT NULL DEFAULT '',
  captured_text TEXT NOT NULL DEFAULT '',
  embedding vector(384),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(query, '') || ' ' || coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(captured_text, ''))
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, research_record_id),
  UNIQUE (research_record_id),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_sessions (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  session_id UUID NOT NULL DEFAULT gen_random_uuid(),
  title TEXT NOT NULL DEFAULT 'Untitled chat',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, session_id),
  UNIQUE (session_id),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  message_id UUID NOT NULL DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(role, '') || ' ' || coalesce(content, ''))
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, message_id),
  UNIQUE (message_id),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE,
  FOREIGN KEY (profile_id, session_id) REFERENCES chat_sessions (profile_id, session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_runs (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  run_id UUID NOT NULL DEFAULT gen_random_uuid(),
  task_id UUID,
  harness TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  goal TEXT NOT NULL DEFAULT '',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, run_id),
  UNIQUE (run_id),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE,
  FOREIGN KEY (profile_id, task_id) REFERENCES tasks (profile_id, task_id) ON DELETE SET NULL (task_id)
);

CREATE TABLE IF NOT EXISTS agent_run_events (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  event_id UUID NOT NULL DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL,
  sequence INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(event_type, '') || ' ' || coalesce(message, ''))
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, event_id),
  UNIQUE (event_id),
  UNIQUE (profile_id, run_id, sequence),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE,
  FOREIGN KEY (profile_id, run_id) REFERENCES agent_runs (profile_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
  profile_id TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  setting_key TEXT NOT NULL,
  setting_value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, setting_key),
  FOREIGN KEY (profile_id, profile_name) REFERENCES profile_metadata (profile_id, profile_name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notes_profile_updated_at
  ON notes (profile_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_search_vector
  ON notes USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_notes_tags
  ON notes USING gin (tags);

CREATE INDEX IF NOT EXISTS idx_tasks_profile_status
  ON tasks (profile_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_search_vector
  ON tasks USING gin (search_vector);

CREATE INDEX IF NOT EXISTS idx_memory_events_profile_created_at
  ON memory_events (profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_events_search_vector
  ON memory_events USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_memory_events_embedding
  ON memory_events USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_research_records_profile_created_at
  ON research_records (profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_records_search_vector
  ON research_records USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_research_records_embedding
  ON research_records USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_profile_updated_at
  ON chat_sessions (profile_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session
  ON chat_messages (profile_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_search_vector
  ON chat_messages USING gin (search_vector);

CREATE INDEX IF NOT EXISTS idx_agent_runs_profile_status
  ON agent_runs (profile_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_run_events_run
  ON agent_run_events (profile_id, run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_agent_run_events_search_vector
  ON agent_run_events USING gin (search_vector);

CREATE INDEX IF NOT EXISTS idx_settings_profile_key
  ON settings (profile_id, setting_key);

-- zsper brain initial schema
