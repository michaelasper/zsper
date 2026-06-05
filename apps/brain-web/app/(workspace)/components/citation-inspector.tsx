"use client";

import { useEffect, useMemo, useState } from "react";
import {
  type BrainCitationAnchor,
  type BrainCitationInspectionReport,
  type BrainDocumentInspectionReport,
  type BrainDocumentRecord,
  fetchBrainCitationInspection,
  fetchBrainCitations,
  fetchBrainDocumentInspection,
  fetchBrainDocuments
} from "../../api-client";
import { WorkspaceShell } from "../../workspace-shell";

type CitationWorkspaceMode = "documents" | "citations";

type LoadingState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

export function CitationInspectionWorkspace({
  mode
}: {
  mode: CitationWorkspaceMode;
}) {
  const [documents, setDocuments] = useState<LoadingState<BrainDocumentRecord[]>>({
    data: null,
    error: null,
    loading: mode === "documents"
  });
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [documentInspection, setDocumentInspection] = useState<
    LoadingState<BrainDocumentInspectionReport>
  >({
    data: null,
    error: null,
    loading: false
  });
  const [citations, setCitations] = useState<LoadingState<BrainCitationAnchor[]>>({
    data: null,
    error: null,
    loading: mode === "citations"
  });
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);

  useEffect(() => {
    if (mode !== "citations") {
      return;
    }

    let mounted = true;

    async function loadCitations() {
      try {
        const report = await fetchBrainCitations();
        if (!mounted) {
          return;
        }
        setCitations({
          data: report.citations,
          error: null,
          loading: false
        });
      } catch (error) {
        if (!mounted) {
          return;
        }
        setCitations({
          data: [],
          error: error instanceof Error ? error.message : "Citation request failed",
          loading: false
        });
      }
    }

    void loadCitations();

    return () => {
      mounted = false;
    };
  }, [mode]);

  useEffect(() => {
    if (mode !== "documents") {
      return;
    }

    let mounted = true;

    async function loadDocuments() {
      try {
        const report = await fetchBrainDocuments();
        if (!mounted) {
          return;
        }
        setDocuments({
          data: report.documents,
          error: null,
          loading: false
        });
      } catch (error) {
        if (!mounted) {
          return;
        }
        setDocuments({
          data: [],
          error: error instanceof Error ? error.message : "Document request failed",
          loading: false
        });
      }
    }

    void loadDocuments();

    return () => {
      mounted = false;
    };
  }, [mode]);

  useEffect(() => {
    if (mode !== "documents" || !selectedDocumentId) {
      setDocumentInspection({ data: null, error: null, loading: false });
      return;
    }

    let mounted = true;
    const documentId = selectedDocumentId;

    async function inspectDocument() {
      setDocumentInspection((current) => ({
        data: current.data,
        error: null,
        loading: true
      }));
      try {
        const report = await fetchBrainDocumentInspection(documentId);
        if (!mounted) {
          return;
        }
        setDocumentInspection({ data: report, error: null, loading: false });
      } catch (error) {
        if (!mounted) {
          return;
        }
        setDocumentInspection({
          data: null,
          error:
            error instanceof Error ? error.message : "Document inspection failed",
          loading: false
        });
      }
    }

    void inspectDocument();

    return () => {
      mounted = false;
    };
  }, [mode, selectedDocumentId]);

  function selectDocument(documentId: string) {
    setSelectedDocumentId(documentId);
    setSelectedCitationId(null);
  }

  return (
    <WorkspaceShell
      initialViewKey={mode}
      renderInspector={(view) =>
        view.key === mode ? (
          <CitationInspector citationAnchorId={selectedCitationId} />
        ) : undefined
      }
      renderWorkSurface={(view) =>
        view.key !== mode ? undefined : mode === "citations" ? (
          <CitationListView
            citations={citations}
            selectedCitationId={selectedCitationId}
            onSelectCitation={setSelectedCitationId}
          />
        ) : (
          <DocumentListView
            documentInspection={documentInspection}
            documents={documents}
            onSelectCitation={setSelectedCitationId}
            onSelectDocument={selectDocument}
            selectedCitationId={selectedCitationId}
            selectedDocumentId={selectedDocumentId}
          />
        )
      }
    />
  );
}

export function CitationInspector({
  citationAnchorId
}: {
  citationAnchorId: string | null;
}) {
  const [inspection, setInspection] = useState<
    LoadingState<BrainCitationInspectionReport>
  >({
    data: null,
    error: null,
    loading: false
  });

  useEffect(() => {
    if (!citationAnchorId) {
      setInspection({ data: null, error: null, loading: false });
      return;
    }

    let mounted = true;
    const selectedAnchorId = citationAnchorId;

    async function inspectCitation() {
      setInspection((current) => ({
        data: current.data,
        error: null,
        loading: true
      }));
      try {
        const report = await fetchBrainCitationInspection(selectedAnchorId);
        if (!mounted) {
          return;
        }
        setInspection({ data: report, error: null, loading: false });
      } catch (error) {
        if (!mounted) {
          return;
        }
        setInspection({
          data: null,
          error: error instanceof Error ? error.message : "Citation inspection failed",
          loading: false
        });
      }
    }

    void inspectCitation();

    return () => {
      mounted = false;
    };
  }, [citationAnchorId]);

  return (
    <div className="citation-inspector" data-testid="citation-inspector">
      <div className="inspector-header">
        <p>Inspector</p>
        <h2 data-testid="inspector-heading">Citation source</h2>
      </div>
      {!citationAnchorId ? (
        <div className="inspector-note">No citation selected.</div>
      ) : null}
      {inspection.loading ? <div className="inspector-note">Loading citation.</div> : null}
      {inspection.error ? <div className="api-error">{inspection.error}</div> : null}
      {inspection.data ? <CitationInspectionDetails inspection={inspection.data} /> : null}
    </div>
  );
}

function CitationListView({
  citations,
  onSelectCitation,
  selectedCitationId
}: {
  citations: LoadingState<BrainCitationAnchor[]>;
  onSelectCitation: (citationAnchorId: string) => void;
  selectedCitationId: string | null;
}) {
  if (citations.loading) {
    return <div className="empty-strip">Loading citation anchors.</div>;
  }

  if (citations.error) {
    return <div className="api-error">{citations.error}</div>;
  }

  if (!citations.data || citations.data.length === 0) {
    return <div className="empty-strip">No citation anchors available.</div>;
  }

  return (
    <div className="citation-table-shell">
      <table className="citation-table">
        <thead>
          <tr>
            <th>Anchor</th>
            <th>Document</th>
            <th>Chunk</th>
            <th>Range</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {citations.data.map((citation) => (
            <tr
              data-selected={
                citation.citation_anchor_id === selectedCitationId ? "true" : undefined
              }
              key={citation.citation_anchor_id}
            >
              <td>
                <button
                  className="citation-row-button"
                  onClick={() => onSelectCitation(citation.citation_anchor_id)}
                  type="button"
                >
                  <span>{citation.label}</span>
                  <strong>{citation.citation_anchor_id}</strong>
                </button>
              </td>
              <td>{citation.document_id}</td>
              <td>{citation.chunk_id}</td>
              <td>{citation.display_range ?? "unknown"}</td>
              <td>{citation.source_path_or_url}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentListView({
  documentInspection,
  documents,
  onSelectCitation,
  onSelectDocument,
  selectedCitationId,
  selectedDocumentId
}: {
  documentInspection: LoadingState<BrainDocumentInspectionReport>;
  documents: LoadingState<BrainDocumentRecord[]>;
  onSelectCitation: (citationAnchorId: string) => void;
  onSelectDocument: (documentId: string) => void;
  selectedCitationId: string | null;
  selectedDocumentId: string | null;
}) {
  if (documents.loading) {
    return <div className="empty-strip">Loading document records.</div>;
  }

  if (documents.error) {
    return <div className="api-error">{documents.error}</div>;
  }

  if (!documents.data || documents.data.length === 0) {
    return <div className="empty-strip">No document records available.</div>;
  }

  return (
    <div className="document-inspection-layout">
      <div className="citation-table-shell">
        <table className="document-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Parser</th>
              <th>Source type</th>
              <th>Updated</th>
              <th>Parsed path</th>
            </tr>
          </thead>
          <tbody>
            {documents.data.map((document) => (
              <tr
                data-selected={
                  document.document_id === selectedDocumentId ? "true" : undefined
                }
                key={document.document_id}
              >
                <td>
                  <button
                    className="citation-row-button"
                    onClick={() => onSelectDocument(document.document_id)}
                    type="button"
                  >
                    <span>{document.title}</span>
                    <strong>{document.document_id}</strong>
                  </button>
                </td>
                <td>{document.parser}</td>
                <td>{document.source_type}</td>
                <td>{document.updated_at}</td>
                <td>{document.parsed_representation_path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <DocumentInspectionPanel
        inspection={documentInspection}
        onSelectCitation={onSelectCitation}
        selectedCitationId={selectedCitationId}
        selectedDocumentId={selectedDocumentId}
      />
    </div>
  );
}

function DocumentInspectionPanel({
  inspection,
  onSelectCitation,
  selectedCitationId,
  selectedDocumentId
}: {
  inspection: LoadingState<BrainDocumentInspectionReport>;
  onSelectCitation: (citationAnchorId: string) => void;
  selectedCitationId: string | null;
  selectedDocumentId: string | null;
}) {
  if (!selectedDocumentId) {
    return <div className="empty-strip">Select a document record.</div>;
  }

  if (inspection.loading) {
    return <div className="empty-strip">Loading document chunks.</div>;
  }

  if (inspection.error) {
    return <div className="api-error">{inspection.error}</div>;
  }

  if (!inspection.data) {
    return <div className="empty-strip">No document inspection loaded.</div>;
  }

  const citationsByChunkId = new Map(
    inspection.data.citations.map((citation) => [citation.chunk_id, citation])
  );

  return (
    <div className="document-chunk-list" data-testid="document-chunk-list">
      <div className="record-metadata-grid">
        <div className="inspector-row">
          <span>Document</span>
          <strong>{inspection.data.document.title}</strong>
        </div>
        <div className="inspector-row">
          <span>Chunks</span>
          <strong>{inspection.data.chunk_ids.length}</strong>
        </div>
        <div className="inspector-row">
          <span>Citations</span>
          <strong>{inspection.data.citation_anchor_ids.length}</strong>
        </div>
      </div>
      <div className="citation-table-shell">
        <table className="document-table">
          <thead>
            <tr>
              <th>Chunk</th>
              <th>Tokens</th>
              <th>Bytes</th>
              <th>Citation</th>
            </tr>
          </thead>
          <tbody>
            {inspection.data.chunks.map((chunk) => {
              const citation = citationsByChunkId.get(chunk.chunk_id);
              return (
                <tr
                  data-selected={
                    citation?.citation_anchor_id === selectedCitationId
                      ? "true"
                      : undefined
                  }
                  key={chunk.chunk_id}
                >
                  <td>{chunk.chunk_id}</td>
                  <td>{chunk.token_estimate}</td>
                  <td>{displayByteRange(chunk.byte_start, chunk.byte_end)}</td>
                  <td>
                    {citation ? (
                      <button
                        className="citation-row-button"
                        onClick={() => onSelectCitation(citation.citation_anchor_id)}
                        type="button"
                      >
                        <span>{citation.label}</span>
                        <strong>{citation.citation_anchor_id}</strong>
                      </button>
                    ) : (
                      "missing"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CitationInspectionDetails({
  inspection
}: {
  inspection: BrainCitationInspectionReport;
}) {
  const byteRange = useMemo(
    () =>
      `${inspection.context.citation_start_byte}-${inspection.context.citation_end_byte}`,
    [inspection.context.citation_end_byte, inspection.context.citation_start_byte]
  );

  return (
    <div className="citation-inspector-body">
      <div className="inspector-stack">
        <div className="inspector-row">
          <span>Anchor</span>
          <strong>{inspection.citation_anchor_id}</strong>
        </div>
        <div className="inspector-row">
          <span>Document</span>
          <strong>{inspection.document_id}</strong>
        </div>
        <div className="inspector-row">
          <span>Chunk</span>
          <strong>{inspection.chunk_id}</strong>
        </div>
        <div className="inspector-row">
          <span>Source</span>
          <strong>{inspection.context.source_path_or_url}</strong>
        </div>
        <div className="inspector-row">
          <span>Display range</span>
          <strong>{inspection.context.display_range ?? "unknown"}</strong>
        </div>
        <div className="inspector-row">
          <span>Citation bytes</span>
          <strong>{byteRange}</strong>
        </div>
      </div>
      <section className="citation-text-block">
        <h3>Source context</h3>
        <pre>{inspection.context.text}</pre>
      </section>
      <section className="citation-text-block">
        <h3>Chunk text</h3>
        <pre>{inspection.chunk.text}</pre>
      </section>
    </div>
  );
}

function displayByteRange(start: number | null, end: number | null) {
  if (start === null || end === null) {
    return "unknown";
  }
  return `${start}-${end}`;
}
