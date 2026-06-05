"use client";

import { useEffect, useMemo, useState } from "react";
import {
  type BrainSettingsReport,
  type BrainStatusReport,
  fetchBrainSettings,
  fetchBrainStatus
} from "./api-client";

type ViewKey =
  | "chat"
  | "research"
  | "documents"
  | "citations"
  | "notes"
  | "tasks"
  | "memories"
  | "agent-runs"
  | "settings";

type ViewDefinition = {
  key: ViewKey;
  label: string;
  eyebrow: string;
  summary: string;
  mainKind: "thread" | "list" | "table" | "settings";
  columns?: string[];
  rows: string[][];
  emptyState: string;
  inspectorTitle: string;
  inspectorItems: string[];
};

const views: ViewDefinition[] = [
  {
    key: "chat",
    label: "Chat",
    eyebrow: "Local thread",
    summary: "Grounded conversation queue with citations and profile-local context.",
    mainKind: "thread",
    rows: [
      ["User", "Ask about a local document, note, task, or agent run."],
      ["Assistant", "Responses will show source citations in the inspector."]
    ],
    emptyState: "No active chat session. Start a local thread when chat records land.",
    inspectorTitle: "Context & citations",
    inspectorItems: ["Selected profile context", "Retrieved chunks", "Answer citation anchors"]
  },
  {
    key: "research",
    label: "Research Inbox",
    eyebrow: "Source triage",
    summary: "Saved local search results and captured sources waiting for ingestion.",
    mainKind: "list",
    rows: [
      ["Inbox", "Local SearXNG results appear here before ingestion."],
      ["Ready", "Accepted sources can become document records."]
    ],
    emptyState: "No research captures yet. Future searches will queue here.",
    inspectorTitle: "Source metadata",
    inspectorItems: ["Capture timestamp", "Original query", "Extraction status"]
  },
  {
    key: "documents",
    label: "Documents",
    eyebrow: "RAG library",
    summary: "Document records, parsers, chunk counts, and ingestion status.",
    mainKind: "table",
    columns: ["Title", "Parser", "Chunks", "Status"],
    rows: [
      ["Platform spec", "text", "pending", "placeholder"],
      ["Local runbook", "docling", "pending", "placeholder"]
    ],
    emptyState: "No ingested documents. Markdown, PDF, and web captures will list here.",
    inspectorTitle: "Document chunks",
    inspectorItems: ["Chunk id", "Token estimate", "Citation anchor"]
  },
  {
    key: "citations",
    label: "Citations",
    eyebrow: "Provenance",
    summary: "Citation anchors connecting answers to exact source chunks.",
    mainKind: "table",
    columns: ["Anchor", "Source", "Range", "Confidence"],
    rows: [
      ["doc:001#chunk-04", "Platform spec", "pending", "not scored"],
      ["note:002#anchor-01", "Research note", "pending", "not scored"]
    ],
    emptyState: "No citation anchors yet. RAG answers will create inspectable anchors.",
    inspectorTitle: "Citation preview",
    inspectorItems: ["Source path or URL", "Display range", "Nearby chunk text"]
  },
  {
    key: "notes",
    label: "Notes",
    eyebrow: "Local records",
    summary: "Profile-local notes with tags, backlinks, citations, and task links.",
    mainKind: "list",
    rows: [
      ["Draft", "Notes will support backlinks and Markdown export."],
      ["Linked", "Future records can attach documents, memories, and tasks."]
    ],
    emptyState: "No notes yet. Notes remain canonical Zsper records.",
    inspectorTitle: "Note metadata",
    inspectorItems: ["Tags", "Backlinks", "Linked citations"]
  },
  {
    key: "tasks",
    label: "Tasks",
    eyebrow: "Execution queue",
    summary: "User tasks and agent-executable work tracked by state transitions.",
    mainKind: "table",
    columns: ["Task", "Priority", "Status", "Links"],
    rows: [
      ["Review inbox captures", "normal", "inbox", "research"],
      ["Launch local agent run", "high", "ready", "agent-runs"]
    ],
    emptyState: "No tasks yet. Future tasks can launch through local harness adapters.",
    inspectorTitle: "Task state",
    inspectorItems: ["Status history", "Linked records", "Harness readiness"]
  },
  {
    key: "memories",
    label: "Memories",
    eyebrow: "Provenance log",
    summary: "Canonical memory events with source, confidence, and participants.",
    mainKind: "list",
    rows: [
      ["Preference", "Memory events can be disabled per profile."],
      ["Decision", "Honcho is a sidecar while Zsper keeps the ledger."]
    ],
    emptyState: "No memory events. Future summaries will include provenance.",
    inspectorTitle: "Memory provenance",
    inspectorItems: ["Source record", "Participants", "Confidence"]
  },
  {
    key: "agent-runs",
    label: "Agent Runs",
    eyebrow: "tmux runs",
    summary: "Local agent histories with events, artifacts, summaries, and attach paths.",
    mainKind: "table",
    columns: ["Run", "Harness", "Status", "Last event"],
    rows: [
      ["run-placeholder-01", "pi", "planned", "waiting"],
      ["run-placeholder-02", "opencode", "planned", "waiting"]
    ],
    emptyState: "No runs yet. Launches will stream local events here.",
    inspectorTitle: "Run events",
    inspectorItems: ["stdout", "tool calls", "artifacts"]
  },
  {
    key: "settings",
    label: "Settings",
    eyebrow: "Runtime status",
    summary: "Profile, model, search, database, Redis, and hosted-call guard state.",
    mainKind: "settings",
    rows: [],
    emptyState: "Settings load from the local Brain API status endpoints.",
    inspectorTitle: "Runtime metadata",
    inspectorItems: ["Profile root", "Allowed CORS origins", "Hosted config findings"]
  }
];

const viewByKey = new Map<ViewKey, ViewDefinition>(views.map((view) => [view.key, view]));

export function WorkspaceShell() {
  const [activeViewKey, setActiveViewKey] = useState<ViewKey>("chat");
  const [status, setStatus] = useState<BrainStatusReport | null>(null);
  const [settings, setSettings] = useState<BrainSettingsReport | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadRuntimeState() {
      try {
        const [statusReport, settingsReport] = await Promise.all([
          fetchBrainStatus(),
          fetchBrainSettings()
        ]);
        if (!mounted) {
          return;
        }
        setStatus(statusReport);
        setSettings(settingsReport);
        setApiError(null);
      } catch (error) {
        if (!mounted) {
          return;
        }
        setApiError(error instanceof Error ? error.message : "Brain API request failed");
      }
    }

    void loadRuntimeState();

    return () => {
      mounted = false;
    };
  }, []);

  const activeView = viewByKey.get(activeViewKey) ?? views[0];
  const failedCount = status?.failed_components.length ?? 0;
  const statusTone = status?.overall_status === "pass" ? "pass" : status ? "warn" : "unknown";
  const serviceRows = useMemo(() => {
    return Object.entries(status?.components ?? {});
  }, [status]);

  return (
    <div className="workspace-shell" data-testid="workspace-shell">
      <nav className="left-navigation" data-testid="left-navigation" aria-label="Brain views">
        <div className="nav-header">
          <div className="product-mark">ZB</div>
          <div className="product-copy">
            <p>Zsper Brain</p>
            <span>{settings?.profile.mode ?? "local"}</span>
          </div>
        </div>
        <div className="profile-chip">
          <span className={`status-dot ${statusTone}`} />
          <span>{status?.overall_status ?? "loading"}</span>
          {failedCount > 0 ? <strong>{failedCount}</strong> : null}
        </div>
        <div className="nav-list">
          {views.map((view) => (
            <button
              aria-current={view.key === activeViewKey ? "page" : undefined}
              aria-label={view.label}
              className="nav-item"
              key={view.key}
              onClick={() => setActiveViewKey(view.key)}
              type="button"
            >
              <span className="nav-item-label">{view.label}</span>
              <span className="nav-item-meta">{view.eyebrow}</span>
            </button>
          ))}
        </div>
      </nav>

      <main className="main-work-area" data-testid="main-work-area">
        <header className="view-header">
          <div>
            <p>{activeView.eyebrow}</p>
            <h1 data-testid="active-view-title">{activeView.label}</h1>
          </div>
          <div className="view-status" data-testid="status-summary">
            <span className={`status-dot ${statusTone}`} />
            <span>{status?.overall_status ?? "loading"}</span>
          </div>
        </header>
        <p className="view-summary">{activeView.summary}</p>
        <section className="work-surface" data-testid="view-placeholder">
          {activeView.mainKind === "thread" ? <ThreadView view={activeView} /> : null}
          {activeView.mainKind === "list" ? <ListView view={activeView} /> : null}
          {activeView.mainKind === "table" ? <TableView view={activeView} /> : null}
          {activeView.mainKind === "settings" ? (
            <SettingsView
              apiError={apiError}
              serviceRows={serviceRows}
              settings={settings}
              status={status}
            />
          ) : null}
        </section>
      </main>

      <aside className="right-inspector" data-testid="right-inspector">
        <div className="inspector-header">
          <p>Inspector</p>
          <h2 data-testid="inspector-heading">{activeView.inspectorTitle}</h2>
        </div>
        <div className="inspector-stack">
          {activeView.inspectorItems.map((item) => (
            <div className="inspector-row" key={item}>
              <span>{item}</span>
              <strong>pending</strong>
            </div>
          ))}
        </div>
        {activeView.key === "settings" ? (
          <RuntimeInspector apiError={apiError} settings={settings} status={status} />
        ) : (
          <div className="inspector-note">
            Select a record in this view to inspect metadata, citations, chunks, or run events.
          </div>
        )}
      </aside>
    </div>
  );
}

function ThreadView({ view }: { view: ViewDefinition }) {
  return (
    <div className="thread-stack">
      {view.rows.map(([speaker, body]) => (
        <article className="thread-message" key={`${speaker}-${body}`}>
          <span>{speaker}</span>
          <p>{body}</p>
        </article>
      ))}
      <div className="empty-strip">{view.emptyState}</div>
    </div>
  );
}

function ListView({ view }: { view: ViewDefinition }) {
  return (
    <div className="record-list">
      {view.rows.map(([label, body]) => (
        <article className="record-row" key={`${label}-${body}`}>
          <span>{label}</span>
          <p>{body}</p>
        </article>
      ))}
      <div className="empty-strip">{view.emptyState}</div>
    </div>
  );
}

function TableView({ view }: { view: ViewDefinition }) {
  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            {(view.columns ?? []).map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {view.rows.map((row) => (
            <tr key={row.join("-")}>
              {row.map((cell) => (
                <td key={cell}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="empty-strip">{view.emptyState}</div>
    </div>
  );
}

function SettingsView({
  apiError,
  serviceRows,
  settings,
  status
}: {
  apiError: string | null;
  serviceRows: [string, string][];
  settings: BrainSettingsReport | null;
  status: BrainStatusReport | null;
}) {
  return (
    <div className="settings-grid">
      {apiError ? <div className="api-error">{apiError}</div> : null}
      <section className="settings-block" data-testid="settings-profile">
        <h3>Profile</h3>
        <dl>
          <dt>ID</dt>
          <dd>{settings?.profile.id ?? "loading"}</dd>
          <dt>Mode</dt>
          <dd>{settings?.profile.mode ?? "loading"}</dd>
          <dt>Network</dt>
          <dd>{settings?.profile.network_policy ?? "loading"}</dd>
          <dt>Storage</dt>
          <dd>{settings?.profile.storage_backend ?? "loading"}</dd>
        </dl>
      </section>
      <section className="settings-block" data-testid="settings-model">
        <h3>Model</h3>
        <dl>
          <dt>Base URL</dt>
          <dd>{settings?.model.base_url ?? "loading"}</dd>
          <dt>Model profile</dt>
          <dd>{settings?.profile.model_profile ?? "loading"}</dd>
          <dt>Hosted</dt>
          <dd>{settings ? String(settings.model.hosted) : "loading"}</dd>
        </dl>
      </section>
      <section className="settings-block settings-services" data-testid="settings-services">
        <h3>Services</h3>
        <div className="service-list">
          {serviceRows.length > 0 ? (
            serviceRows.map(([name, value]) => (
              <div className="service-row" key={name}>
                <span>{name.replaceAll("_", " ")}</span>
                <strong>{value}</strong>
              </div>
            ))
          ) : (
            <div className="empty-strip">Loading service status from Brain API.</div>
          )}
        </div>
      </section>
      <section className="settings-block">
        <h3>Search</h3>
        <dl>
          <dt>SearXNG</dt>
          <dd>{settings?.search.searxng_url ?? "not configured"}</dd>
          <dt>Enabled</dt>
          <dd>{settings ? String(settings.search.searxng_enabled) : "loading"}</dd>
          <dt>Hosted guard</dt>
          <dd>{settings?.hosted_config.status ?? status?.overall_status ?? "loading"}</dd>
        </dl>
      </section>
    </div>
  );
}

function RuntimeInspector({
  apiError,
  settings,
  status
}: {
  apiError: string | null;
  settings: BrainSettingsReport | null;
  status: BrainStatusReport | null;
}) {
  return (
    <div className="runtime-inspector">
      <div className="inspector-row">
        <span>Profile</span>
        <strong>{settings?.profile.id ?? status?.profile_id ?? "loading"}</strong>
      </div>
      <div className="inspector-row">
        <span>Database</span>
        <strong>{settings?.database.name ?? "loading"}</strong>
      </div>
      <div className="inspector-row">
        <span>Redis prefix</span>
        <strong>{settings?.redis.key_prefix ?? "loading"}</strong>
      </div>
      <div className="inspector-row">
        <span>Brain API</span>
        <strong>{settings?.brain_api.url ?? "loading"}</strong>
      </div>
      <div className="inspector-row">
        <span>Error</span>
        <strong>{apiError ?? "none"}</strong>
      </div>
    </div>
  );
}
