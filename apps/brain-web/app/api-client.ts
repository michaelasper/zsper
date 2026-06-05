export type BrainStatusValue = "pass" | "fail" | "disabled" | "unknown" | string;

export type BrainStatusReport = {
  profile_id: string;
  overall_status: BrainStatusValue;
  components: Record<string, BrainStatusValue>;
  failed_components: string[];
  unknown_components: string[];
  disabled_components: string[];
};

export type BrainSettingsReport = {
  profile_id: string;
  profile: {
    id: string;
    name: string;
    mode: string;
    root: string;
    network_policy: string;
    storage_backend: string;
    model_profile: string;
    embedding_profile: string;
  };
  database: {
    profile_id: string;
    name: string;
    dsn: string;
  };
  redis: {
    profile_id: string;
    url: string;
    key_prefix: string;
  };
  model: {
    base_url: string;
    models_url: string;
    hosted: boolean;
  };
  search: {
    searxng_url: string | null;
    searxng_enabled: boolean;
    hosted: boolean;
  };
  extraction: {
    base_url: string | null;
    hosted: boolean;
  };
  honcho: {
    url: string | null;
    enabled: boolean;
  };
  brain_api: {
    url: string | null;
  };
  web_ui: {
    url: string | null;
    available: boolean;
  };
  cors: {
    allowed_origins: string[];
  };
  hosted_config: {
    status: BrainStatusValue;
    findings: string[];
  };
};

export type BrainDocumentRecord = {
  id: string;
  document_id: string;
  profile_id: string;
  source_type: string;
  raw_asset_path: string;
  parsed_representation_path: string;
  title: string;
  metadata: Record<string, unknown>;
  content_hash: string;
  parser: string;
  created_at: string;
  updated_at: string;
};

export type BrainDocumentChunk = {
  id: string;
  chunk_id: string;
  document_id: string;
  profile_id: string;
  chunk_index: number;
  text: string;
  citation_anchor_id: string;
  token_estimate: number;
  byte_start: number | null;
  byte_end: number | null;
  embedding_model: string | null;
  embedding_vector_id: string | null;
};

export type BrainCitationAnchor = {
  id: string;
  citation_anchor_id: string;
  profile_id: string;
  document_id: string;
  chunk_id: string;
  label: string;
  source_path_or_url: string;
  display_range: string | null;
};

export type BrainCitationListReport = {
  profile_id: string;
  document_id?: string;
  citation_anchor_ids: string[];
  citations: BrainCitationAnchor[];
};

export type BrainDocumentListReport = {
  profile_id: string;
  document_ids: string[];
  documents: BrainDocumentRecord[];
};

export type BrainDocumentInspectionReport = {
  profile_id: string;
  document_id: string;
  document: BrainDocumentRecord;
  chunk_ids: string[];
  citation_anchor_ids: string[];
  chunks: BrainDocumentChunk[];
  citations: BrainCitationAnchor[];
};

export type BrainCitationInspectionReport = {
  profile_id: string;
  document_id: string;
  chunk_id: string;
  citation_anchor_id: string;
  citation: BrainCitationAnchor;
  chunk: BrainDocumentChunk;
  context: {
    source_path_or_url: string;
    display_range: string | null;
    text: string;
    citation_text: string;
    context_start_byte: number;
    context_end_byte: number;
    citation_start_byte: number;
    citation_end_byte: number;
  };
};

export type BrainAnswerCitation = {
  document_id: string;
  chunk_id: string;
  citation_anchor_id: string;
  source_path_or_url: string;
  display_range: string | null;
  text_preview: string;
  citation_confidence: number;
};

export type BrainAnswerResult = {
  profile_id: string;
  question: string;
  text: string;
  answer_confidence: number;
  citations: BrainAnswerCitation[];
  model: string;
};

export type BrainChatReport = {
  profile_id: string;
  question: string;
  limit: number;
  result_count: number;
  answer: BrainAnswerResult;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_BRAIN_API_BASE_URL?.replace(/\/$/, "") ?? "";

export async function fetchBrainStatus(): Promise<BrainStatusReport> {
  return fetchJson<BrainStatusReport>("/api/status");
}

export async function fetchBrainSettings(): Promise<BrainSettingsReport> {
  return fetchJson<BrainSettingsReport>("/api/settings");
}

export async function fetchBrainCitations(
  documentId?: string
): Promise<BrainCitationListReport> {
  const query = documentId ? `?document_id=${encodeURIComponent(documentId)}` : "";
  return fetchJson<BrainCitationListReport>(`/api/citations${query}`);
}

export async function fetchBrainDocuments(): Promise<BrainDocumentListReport> {
  return fetchJson<BrainDocumentListReport>("/api/documents");
}

export async function fetchBrainDocumentInspection(
  documentId: string
): Promise<BrainDocumentInspectionReport> {
  return fetchJson<BrainDocumentInspectionReport>(
    `/api/documents/${encodeURIComponent(documentId)}/inspect`
  );
}

export async function fetchBrainCitationInspection(
  citationAnchorId: string,
  contextChars = 160
): Promise<BrainCitationInspectionReport> {
  return fetchJson<BrainCitationInspectionReport>(
    `/api/citations/${encodeURIComponent(
      citationAnchorId
    )}/inspect?context_chars=${contextChars}`
  );
}

export async function requestBrainChat(
  question: string,
  limit = 10
): Promise<BrainChatReport> {
  return fetchJson<BrainChatReport>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ question, limit })
  });
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers
    }
  });

  if (!response.ok) {
    throw new Error(`Brain API ${path} returned HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}
