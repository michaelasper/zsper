import { expect, test } from "@playwright/test";

const statusResponse = {
  profile_id: "work",
  overall_status: "pass",
  components: {
    profile_schema: "pass",
    writable_dirs: "pass",
    database: "pass",
    redis: "pass",
    searxng: "pass",
    honcho: "pass",
    local_model_models: "pass",
    brain_api: "pass",
    web_ui: "pass",
    forbidden_hosted_config: "pass"
  },
  failed_components: [],
  unknown_components: [],
  disabled_components: []
};

const settingsResponse = {
  profile_id: "work",
  profile: {
    id: "work",
    name: "work",
    mode: "work",
    root: "/tmp/zsper-work",
    network_policy: "local-first",
    storage_backend: "postgres-pgvector",
    model_profile: "zsper-qwen35-oq6-fp16-mtp-omlx-128k",
    embedding_profile: "local-bge-small-en-v1.5"
  },
  database: {
    profile_id: "work",
    name: "zsper_work",
    dsn: "postgresql://zsper:***@127.0.0.1:5432/zsper_work"
  },
  redis: {
    profile_id: "work",
    url: "redis://127.0.0.1:6379/0",
    key_prefix: "zsper:work:"
  },
  model: {
    base_url: "http://127.0.0.1:9127/v1",
    models_url: "http://127.0.0.1:9127/v1/models",
    hosted: false
  },
  search: {
    searxng_url: "http://127.0.0.1:8080",
    searxng_enabled: true,
    hosted: false
  },
  extraction: {
    base_url: null,
    hosted: false
  },
  honcho: {
    url: "http://127.0.0.1:8001",
    enabled: true
  },
  brain_api: {
    url: "http://127.0.0.1:7420"
  },
  web_ui: {
    url: "http://127.0.0.1:7421",
    available: true
  },
  cors: {
    allowed_origins: ["http://127.0.0.1:7421"]
  },
  hosted_config: {
    status: "pass",
    findings: []
  }
};

const citation = {
  id: "anchor-target",
  profile_id: "work",
  citation_anchor_id: "anchor-target",
  document_id: "doc-work",
  chunk_id: "chunk-target",
  label: "Fixture chunk",
  source_path_or_url: "/fixtures/source.txt",
  display_range: "bytes 10-22"
};

const documentRecord = {
  id: "doc-work",
  document_id: "doc-work",
  profile_id: "work",
  source_type: "file",
  raw_asset_path: "/fixtures/source.md",
  parsed_representation_path: "/fixtures/source.txt",
  title: "Work Document",
  metadata: {
    parser_version: "fixture"
  },
  content_hash: "sha256:fixture",
  parser: "text",
  created_at: "2026-06-04T12:00:00Z",
  updated_at: "2026-06-04T12:03:00Z"
};

const chunk = {
  id: "chunk-target",
  profile_id: "work",
  chunk_id: "chunk-target",
  document_id: "doc-work",
  chunk_index: 0,
  text: "Document chunk exact sentence TARGET-CHUNK.",
  citation_anchor_id: "anchor-target",
  token_estimate: 8,
  byte_start: 5,
  byte_end: 27,
  embedding_model: null,
  embedding_vector_id: null
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/status", async (route) => {
    await route.fulfill({ json: statusResponse });
  });
  await page.route("**/api/settings", async (route) => {
    await route.fulfill({ json: settingsResponse });
  });
  await page.route("**/api/chat", async (route) => {
    await route.fulfill({
      json: {
        profile_id: "work",
        question: "recover worker",
        limit: 10,
        result_count: 1,
        answer: {
          profile_id: "work",
          question: "recover worker",
          text: "Restart the profile worker first.",
          answer_confidence: 0.82,
          citations: [
            {
              document_id: citation.document_id,
              chunk_id: citation.chunk_id,
              citation_anchor_id: citation.citation_anchor_id,
              source_path_or_url: citation.source_path_or_url,
              display_range: citation.display_range,
              text_preview: "Document chunk exact sentence TARGET-CHUNK.",
              citation_confidence: 0.91
            }
          ],
          model: "zsper-qwen35-oq6-fp16-mtp-omlx-128k"
        }
      }
    });
  });
  await page.route("**/api/documents", async (route) => {
    await route.fulfill({
      json: {
        profile_id: "work",
        document_ids: [documentRecord.document_id],
        documents: [documentRecord]
      }
    });
  });
  await page.route("**/api/documents/doc-work/inspect", async (route) => {
    await route.fulfill({
      json: {
        profile_id: "work",
        document_id: "doc-work",
        document: documentRecord,
        chunk_ids: [chunk.chunk_id],
        citation_anchor_ids: [citation.citation_anchor_id],
        chunks: [chunk],
        citations: [citation]
      }
    });
  });
  await page.route("**/api/citations**", async (route) => {
    await route.fulfill({
      json: {
        profile_id: "work",
        citation_anchor_ids: [citation.citation_anchor_id],
        citations: [citation]
      }
    });
  });
  await page.route("**/api/citations/anchor-target/inspect**", async (route) => {
    await route.fulfill({
      json: {
        profile_id: "work",
        document_id: "doc-work",
        chunk_id: "chunk-target",
        citation_anchor_id: "anchor-target",
        citation,
        chunk,
        context: {
          source_path_or_url: "/fixtures/source.txt",
          display_range: "bytes 10-22",
          text: "bbbTARGET-CHUNKccc",
          citation_text: "TARGET-CHUNK",
          context_start_byte: 7,
          context_end_byte: 25,
          citation_start_byte: 10,
          citation_end_byte: 22
        }
      }
    });
  });
});

test("sidebar navigation opens API-backed document and citation routes", async ({
  page
}) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Documents" }).click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.getByRole("button", { name: /Work Document/ })).toBeVisible();

  await page.getByRole("button", { name: "Citations" }).click();
  await expect(page).toHaveURL(/\/citations$/);
  await expect(page.getByRole("button", { name: /Fixture chunk/ })).toBeVisible();
});

test("opens a citation row and shows source context in the inspector", async ({ page }) => {
  await page.goto("/citations");

  await expect(page.getByTestId("active-view-title")).toHaveText("Citations");
  await page.getByRole("button", { name: /Fixture chunk/ }).click();

  await expect(page.getByTestId("citation-inspector")).toContainText(
    "/fixtures/source.txt"
  );
  await expect(page.getByTestId("citation-inspector")).toContainText("bytes 10-22");
  await expect(page.getByTestId("citation-inspector")).toContainText(
    "bbbTARGET-CHUNKccc"
  );
  await expect(page.getByTestId("citation-inspector")).toContainText(
    "Document chunk exact sentence TARGET-CHUNK."
  );
});

test("opens a document citation and reuses the citation inspector", async ({ page }) => {
  await page.goto("/documents");

  await expect(page.getByTestId("active-view-title")).toHaveText("Documents");
  await page.getByRole("button", { name: /Work Document/ }).click();
  await expect(page.getByTestId("document-chunk-list")).toContainText("chunk-target");

  await page.getByRole("button", { name: /Fixture chunk/ }).click();

  await expect(page.getByTestId("citation-inspector")).toContainText(
    "/fixtures/source.txt"
  );
  await expect(page.getByTestId("citation-inspector")).toContainText("bytes 10-22");
  await expect(page.getByTestId("citation-inspector")).toContainText(
    "bbbTARGET-CHUNKccc"
  );
});

test("opens an answer citation in the shared citation inspector", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Chat question").fill("recover worker");
  await page.getByTestId("view-placeholder").getByRole("button", { name: "Ask" }).click();

  await expect(page.getByTestId("chat-answer")).toContainText(
    "Restart the profile worker first."
  );
  await page.getByRole("button", { name: /anchor-target/ }).click();

  await expect(page.getByTestId("citation-inspector")).toContainText(
    "/fixtures/source.txt"
  );
  await expect(page.getByTestId("citation-inspector")).toContainText("bytes 10-22");
  await expect(page.getByTestId("citation-inspector")).toContainText(
    "bbbTARGET-CHUNKccc"
  );
});
