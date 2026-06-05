# Phase 4 Progress

Source plan: `docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md`

Milestone: M4 Documents, RAG, And Citations

## Status

| Task | Title | Dependencies | Status | Verification | Review | Commit |
| --- | --- | --- | --- | --- | --- | --- |
| RAG-001 | RAG Store And Models | BRAIN-002, BRAIN-004, GATE-001 | Complete | `pytest tests/unit/rag/test_store.py tests/unit/test_phase4_progress_doc.py -q` -> 8 passed | PASS | `feat(rag): add document store` |
| RAG-002 | Raw Asset Capture | RAG-001 | Complete | `pytest tests/unit/rag/test_assets.py -q` -> 3 passed | PASS | `feat(rag): add asset capture and policy gates` |
| RAG-003 | RAG Policy Gate | SEC-002, RAG-001 | Complete | `pytest tests/unit/rag/test_policy.py -q` -> 10 passed | PASS | `feat(rag): add asset capture and policy gates` |
| RAG-004 | Parser Selector And Text Parser | RAG-002, RAG-003 | Complete | `pytest tests/unit/rag/test_parser_selector.py -q` -> 26 passed | PASS | `feat(rag): add parser selection` |
| RAG-005 | Docling Parser Adapter | RAG-004 | Complete | `pytest tests/unit/rag/test_docling_parser.py -q` -> 4 passed | PASS | `feat(rag): add docling and web capture` |
| RAG-006 | Local Web Capture And Research Bridge | RAG-003, RAG-004 | Complete | `pytest tests/unit/rag/test_web_capture.py -q` -> 17 passed | PASS | `feat(rag): add docling and web capture` |
| RAG-007 | Deterministic Chunking | RAG-004, RAG-005, RAG-006 | Complete | `pytest tests/unit/rag/test_chunking.py -q` -> 4 passed | PASS | `feat(rag): add deterministic chunking` |
| RAG-008 | Citation Anchor Generation | RAG-007 | Complete | `pytest tests/unit/rag/test_citations.py -q` -> 5 passed | PASS | `feat(rag): add citations embeddings and bm25` |
| RAG-009 | Local Embedding Worker | RAG-007, SEC-002 | Complete | `pytest tests/unit/rag/test_embeddings.py -q` -> 4 passed | PASS | `feat(rag): add citations embeddings and bm25` |
| RAG-010 | BM25 Index | RAG-007 | Complete | `pytest tests/unit/rag/test_bm25.py -q` -> 3 passed | PASS | `feat(rag): add citations embeddings and bm25` |
| RAG-011 | Dense Vector Index | RAG-009, BRAIN-002 | Complete | `pytest tests/unit/rag/test_vector_index.py tests/integration/rag/test_pgvector.py -q` -> 5 passed, 1 skipped | PASS | `feat(rag): add vector index and documents api` |
| RAG-012 | Hybrid Search | RAG-010, RAG-011 | Complete | `pytest tests/unit/rag/test_hybrid_search.py -q` -> 6 passed | PASS | `feat(rag): add hybrid search` |
| RAG-013 | Citation-Grounded Answer Flow | RAG-008, RAG-012, CODE-001 | Complete | `pytest tests/unit/rag/test_answer.py -q` -> 7 passed | PASS | `feat(rag): add citation-grounded answers` |
| RAG-014 | Documents And Citations API | RAG-008, BRAIN-005 | Complete | `pytest tests/unit/brain/test_documents_citations_api.py -q` -> 4 passed | PASS | `feat(rag): add vector index and documents api` |
| RAG-015 | Brain Ingest/Search/Answer CLI | RAG-012, RAG-013, RAG-014, FND-004 | Complete | `pytest tests/unit/brain/test_rag_cli.py -q` -> 7 passed | PASS | `feat(cli): add brain rag commands` |
| RAG-016 | Citation Inspection UI | BRAIN-008, RAG-013, RAG-014 | Complete | `npm --prefix apps/brain-web test` -> 9 passed | PASS | `feat(brain-web): add citation inspection` |
| GATE-002 | RAG Acceptance Suite | RAG-015, RAG-016 | Pending | Pending | Pending | Pending |

## Orchestration Notes

- 2026-06-05: Started Phase 4 from the DAG after `GATE-001` was complete.
- `RAG-001` is the initial critical-path task. It must establish profile-scoped
  document, chunk, citation anchor, embedding metadata, and mutation ledger
  contracts before capture, policy, and parser tasks depend on it.
- 2026-06-05: Implemented and reviewed `RAG-001`. First reviewer pass failed
  because Postgres/pgvector support was only a schema string. Implementer added
  an injectable Postgres backend with pgvector schema initialization,
  profile-scoped persistence/read queries, and fake-connection tests while
  preserving the SQLite file-only path. Review passed after fix. Local
  verification: `pytest tests/unit/rag/test_store.py tests/unit/test_phase4_progress_doc.py -q`
  -> 8 passed; `pytest tests/unit -q` -> 227 passed, 1 FastAPI/Starlette
  TestClient deprecation warning; `ruff check .` -> passed.
- Parallelization point: after `RAG-001`, dispatch `RAG-002` and `RAG-003` in
  parallel because raw asset capture and policy gates have disjoint files.
- 2026-06-05: Implemented `RAG-002` and `RAG-003` in parallel after
  `RAG-001`. `RAG-002` added immutable profile-local raw asset capture,
  content hashing, document metadata, dedupe for unchanged local files, and
  traversal protection. `RAG-003` added policy gates for URL ingest, SearXNG,
  hosted extraction/model/search dependencies, and model downloads. Both
  reviewer passes returned PASS. Local verification:
  `pytest tests/unit/rag/test_assets.py tests/unit/rag/test_policy.py tests/unit/rag/test_store.py -q`
  -> 20 passed.
- 2026-06-05: Implemented and reviewed `RAG-004`. Parser selection routes text,
  Markdown, JSON, YAML, and source files to the local text parser; PDFs, Office
  files, and complex HTML to future Docling; allowed URLs to future web capture;
  and repo paths to future repo parsing. Local verification:
  `pytest tests/unit/rag/test_parser_selector.py tests/unit/rag/test_assets.py tests/unit/rag/test_policy.py -q`
  -> 39 passed.
- 2026-06-05: Implemented and reviewed `RAG-005` and `RAG-006` in parallel after
  `RAG-004`. `RAG-005` added a local, fakeable Docling parser adapter that
  writes normalized parsed JSON under `brain/parsed`, preserves page, heading,
  section, label, and level metadata, and returns parser failure records without
  creating chunks or partial parsed files. Review found missing Docling
  `section_header` handling; the implementer added a regression test and fix.
  `RAG-006` added explicit, policy-gated web capture and selected research
  record ingestion into raw URL assets without auto-parsing. Review found
  secret-bearing source/final URL leakage risks through document ledgers; the
  implementers added pre-write rejection for userinfo, sensitive query keys, and
  sensitive fragment keys while preserving benign fragments. Local verification:
  `pytest tests/unit/rag/test_docling_parser.py tests/unit/rag/test_web_capture.py -q`
  -> 21 passed.
- 2026-06-05: Implemented and reviewed `RAG-007`. Deterministic chunking now
  consumes plain text and Docling parsed representations, persists
  profile-scoped `DocumentChunk` rows with stable IDs, token estimates, and byte
  offsets, and returns sidecar parser location metadata for the future citation
  anchor task. Local verification:
  `pytest tests/unit/rag/test_chunking.py tests/unit/rag/test_docling_parser.py tests/unit/rag/test_parser_selector.py tests/unit/rag/test_store.py -q`
  -> 41 passed.
- Parallelization point: after `RAG-007`, dispatch `RAG-008`, `RAG-009`, and
  `RAG-010` in parallel where write scopes remain disjoint.
- 2026-06-05: Implemented and reviewed `RAG-008`, `RAG-009`, and `RAG-010` in
  parallel after `RAG-007`. `RAG-008` generates one profile-scoped citation
  anchor per chunk and bounded source inspection; review found a parsed-path
  isolation gap, and the implementer added active-profile `brain/parsed` path
  validation plus a cross-profile regression test. `RAG-009` adds local
  embedding metadata generation with deterministic fake/local providers,
  profile `embedding_profile` enforcement, and hosted settings rejection.
  `RAG-010` adds a profile-scoped SQLite/FTS5 BM25 index over chunk text and
  metadata for exact path and error retrieval. Local verification:
  `pytest tests/unit/rag/test_citations.py tests/unit/rag/test_embeddings.py tests/unit/rag/test_bm25.py tests/unit/rag/test_chunking.py tests/unit/rag/test_store.py -q`
  -> 23 passed.
- 2026-06-05: Implemented and reviewed `RAG-011` and `RAG-014` in parallel
  after their prerequisites were available. `RAG-011` adds SQLite-compatible and
  pgvector-backed dense vector indexing with profile-scoped vector rows and
  deterministic local test vectors; the live pgvector smoke test is skipped
  unless `ZSPER_TEST_PGVECTOR_DSN` is configured. `RAG-014` adds Brain API
  document and citation routes for listing, inspection, bounded source context,
  audit ids, redacted document metadata, and cross-profile rejection. Local
  verification:
  `pytest tests/unit/rag/test_vector_index.py tests/integration/rag/test_pgvector.py tests/unit/brain/test_documents_citations_api.py -q`
  -> 9 passed, 1 skipped.
- 2026-06-05: Implemented and reviewed `RAG-012`. Hybrid search now combines
  BM25 and dense vector candidates, returns chunk/citation/source ids with score
  components and previews, exposes `/api/search`, and routes `zsper brain search`
  through hybrid search for all resolved profiles. Review found that air CLI
  search still used exact-only offline search and sqlite-local API dependencies
  could pick Postgres; the implementer made hybrid search the default for air
  too and aligned RAG/vector index defaults on profile-local SQLite paths. Local
  verification:
  `pytest tests/unit/rag/test_hybrid_search.py tests/unit/rag/test_bm25.py tests/unit/rag/test_vector_index.py tests/unit/rag/test_citations.py -q`
  -> 18 passed.
- 2026-06-05: Implemented and reviewed `RAG-013`. Citation-grounded answers now
  search retrieved chunks, call the local OpenAI-compatible chat completions
  endpoint, and return structured citation objects with document, chunk,
  citation anchor, source, range, preview, answer confidence, and separate
  citation confidence. Review found two grounding gaps: empty retrieval could
  still call the model, and the prompt sent only preview text. The fix now
  requires retrieved context before model calls and sends full stored chunk text
  to the model while keeping public citations compact. Local verification:
  `pytest tests/unit/test_cli_help.py tests/unit/rag/test_answer.py -q`
  -> 25 passed.
- 2026-06-05: Implemented and reviewed `RAG-015` and `RAG-016` in parallel
  after `RAG-013` unlocked both tasks. `RAG-015` moves brain RAG CLI handlers
  into `src/zsper/brain/rag_commands.py` and runs ingest through policy, local
  asset capture or allowed web capture, parsing, deterministic chunking,
  citation anchor creation, local embeddings, BM25 indexing, and vector
  indexing before search/answer use hybrid retrieval and structured citations.
  Review found remote Postgres DSNs and libpq `host`/`hostaddr` query params
  could bypass local-only storage policy, and implemented command help still
  read as placeholders; both were fixed with regression tests. `RAG-016` adds
  `/documents` and `/citations` Brain web routes plus a shared citation
  inspector that can open source context from citation rows, document chunk
  citations, and answer citation buttons. Review found sidebar navigation could
  stay on placeholder shell views and chat answers had no inspector path; both
  were fixed. Local verification: `pytest tests/unit/brain/test_rag_cli.py -q`
  -> 7 passed; `npm --prefix apps/brain-web test` -> 9 passed; standalone
  `npm --prefix apps/brain-web run build` -> passed.

## Acceptance Gates

- Every stored RAG record is profile scoped.
- Work and personal profiles cannot read each other's documents, chunks,
  citation anchors, embeddings, raw assets, parsed outputs, indexes, or answer
  contexts.
- Mutating document flows append profile-local JSONL ledger records while
  preserving Postgres/pgvector as the online canonical store target.
- Air profiles keep a SQLite-compatible/file-only iteration path.
- Retrieval remains hybrid BM25 plus dense vectors; dense-only core retrieval is
  not acceptable.
- Any answer that uses retrieved context returns exact citation objects with
  document id, chunk id, citation anchor id, source path or URL, and available
  range/preview fields.
