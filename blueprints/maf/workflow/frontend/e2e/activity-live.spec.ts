import { expect, test } from "@playwright/test";

test("bearer stream triggers snapshot reconciliation of older activity", async ({ page }) => {
  let updated = false;
  const authorizations: string[] = [];
  await page.route("**/api/cases/*/activity**", async (route) => {
    const request = route.request();
    authorizations.push(request.headers().authorization ?? "");
    if (new URL(request.url()).pathname.endsWith("/stream")) {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: "event: activity.refresh\ndata: {}\n\n",
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: "workflow-activity/1",
        items: [
          { type: "created", created_at: "2026-01-02T03:04:05+00:00" },
          ...(updated ? [{ type: "action_failed", created_at: "2026-01-01T03:04:05+00:00" }] : []),
        ],
        next_cursor: null,
      }),
    });
  });
  await page.goto("/e2e/activity-live.html");
  await expect(page.getByText("Workflow created")).toBeVisible();
  updated = true;
  await expect(page.getByText("Action failed")).toBeVisible({ timeout: 12_000 });
  expect(authorizations.length).toBeGreaterThan(2);
  expect(authorizations.every((value) => value === "Bearer synthetic-token")).toBe(true);
  await expect(page.getByText("Workflow created")).toHaveCount(1);
});
