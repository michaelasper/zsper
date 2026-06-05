import { expect, type Locator, type Page, test } from "@playwright/test";

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

const views = [
  "Chat",
  "Research Inbox",
  "Documents",
  "Citations",
  "Notes",
  "Tasks",
  "Memories",
  "Agent Runs",
  "Settings"
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/status", async (route) => {
    await route.fulfill({ json: statusResponse });
  });
  await page.route("**/api/settings", async (route) => {
    await route.fulfill({ json: settingsResponse });
  });
});

test("renders an operational workspace with persistent navigation and inspector", async ({
  page
}) => {
  await page.goto("/");

  await expect(page.getByTestId("workspace-shell")).toBeVisible();
  await expect(page.getByTestId("left-navigation")).toBeVisible();
  await expect(page.getByTestId("main-work-area")).toBeVisible();
  await expect(page.getByTestId("right-inspector")).toBeVisible();

  for (const view of views) {
    const navItem = page.getByRole("button", { name: view });
    await expect(navItem).toBeVisible();
    await navItem.click();

    await expect(page.getByTestId("active-view-title")).toHaveText(view);
    await expect(page.getByTestId("view-placeholder")).toBeVisible();
    await expect(page.getByTestId("inspector-heading")).toBeVisible();
  }
});

test("loads settings and status from mocked Brain API responses", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings" }).click();

  await expect(page.getByTestId("status-summary")).toContainText("pass");
  await expect(page.getByTestId("settings-profile")).toContainText("work");
  await expect(page.getByTestId("settings-profile")).toContainText("local-first");
  await expect(page.getByTestId("settings-model")).toContainText(
    "http://127.0.0.1:9127/v1"
  );
  await expect(page.getByTestId("settings-services")).toContainText("database");
  await expect(page.getByTestId("settings-services")).toContainText("redis");
});

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 }
]) {
  test(`does not overlap shell regions at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/");
    await page.getByRole("button", { name: "Settings" }).click();

    await expectNoPageHorizontalOverflow(page);
    await expectRegionsDoNotOverlap([
      page.getByTestId("left-navigation"),
      page.getByTestId("main-work-area"),
      page.getByTestId("right-inspector")
    ]);
  });
}

async function expectNoPageHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    return document.documentElement.scrollWidth - window.innerWidth;
  });
  expect(overflow).toBeLessThanOrEqual(1);
}

async function expectRegionsDoNotOverlap(regions: Locator[]) {
  const boxes = await Promise.all(
    regions.map(async (region) => {
      const box = await region.boundingBox();
      expect(box).not.toBeNull();
      expect(box?.width).toBeGreaterThan(0);
      expect(box?.height).toBeGreaterThan(0);
      return box!;
    })
  );

  for (let first = 0; first < boxes.length; first += 1) {
    for (let second = first + 1; second < boxes.length; second += 1) {
      const overlapX = Math.max(
        0,
        Math.min(boxes[first].x + boxes[first].width, boxes[second].x + boxes[second].width) -
          Math.max(boxes[first].x, boxes[second].x)
      );
      const overlapY = Math.max(
        0,
        Math.min(boxes[first].y + boxes[first].height, boxes[second].y + boxes[second].height) -
          Math.max(boxes[first].y, boxes[second].y)
      );

      expect(overlapX * overlapY).toBe(0);
    }
  }
}
