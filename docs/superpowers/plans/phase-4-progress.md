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
| RAG-007 | Deterministic Chunking | RAG-004, RAG-005, RAG-006 | Pending | Pending | Pending | Pending |
| RAG-008 | Citation Anchor Generation | RAG-007 | Pending | Pending | Pending | Pending |
| RAG-009 | Local Embedding Worker | RAG-007, SEC-002 | Pending | Pending | Pending | Pending |
| RAG-010 | BM25 Index | RAG-007 | Pending | Pending | Pending | Pending |
| RAG-011 | Dense Vector Index | RAG-009, BRAIN-002 | Pending | Pending | Pending | Pending |
| RAG-012 | Hybrid Search | RAG-010, RAG-011 | Pending | Pending | Pending | Pending |
| RAG-013 | Citation-Grounded Answer Flow | RAG-008, RAG-012, CODE-001 | Pending | Pending | Pending | Pending |
| RAG-014 | Documents And Citations API | RAG-008, BRAIN-005 | Pending | Pending | Pending | Pending |
| RAG-015 | Brain Ingest/Search/Answer CLI | RAG-012, RAG-013, RAG-014, FND-004 | Pending | Pending | Pending | Pending |
| RAG-016 | Citation Inspection UI | BRAIN-008, RAG-013, RAG-014 | Pending | Pending | Pending | Pending |
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
- Parallelization point: after `RAG-007`, dispatch `RAG-008`, `RAG-009`, and
  `RAG-010` in parallel where write scopes remain disjoint.

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
