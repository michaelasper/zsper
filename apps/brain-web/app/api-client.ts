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

const API_BASE_URL = process.env.NEXT_PUBLIC_BRAIN_API_BASE_URL?.replace(/\/$/, "") ?? "";

export async function fetchBrainStatus(): Promise<BrainStatusReport> {
  return fetchJson<BrainStatusReport>("/api/status");
}

export async function fetchBrainSettings(): Promise<BrainSettingsReport> {
  return fetchJson<BrainSettingsReport>("/api/settings");
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    }
  });

  if (!response.ok) {
    throw new Error(`Brain API ${path} returned HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}
