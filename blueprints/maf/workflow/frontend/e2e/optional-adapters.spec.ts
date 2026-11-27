import { expect, test } from "@playwright/test";

test("evidence remains available while synthetic manual execution is disabled", async ({ page }) => {
  await page.goto("/e2e/optional-adapters.html");
  await expect(page.getByText("Review evidence")).toHaveCount(0);
  await expect(page.getByText("Synthetic assertion failed")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Synthetic manual tests" })).toContainText("Unavailable");
  await expect(page.getByRole("button", { name: "Run synthetic check" })).toHaveCount(0);
  await page.getByText("Open a case").click();
  await page.getByLabel("Case ID").fill("80000000-0000-4000-8000-000000000008");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.getByRole("region", { name: "Review evidence" })).toContainText("Approved synthetic evidence");
  await expect(page.getByText("Not projected")).toHaveCount(0);
  await expect(page.getByText(/Manual tests:/)).toHaveCount(0);
  await expect(page.getByText("Synthetic assertion failed")).toHaveCount(0);
  await expect(page.locator("body")).not.toHaveAttribute("data-manual-test-invoked");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("status", { name: "Case status: completed" })).toBeVisible();
});

test("evidence projection failures do not block the ordinary workflow", async ({ page }) => {
  await page.goto("/e2e/optional-adapters.html?projection-error");
  await page.getByText("Open a case").click();
  await page.getByLabel("Case ID").fill("80000000-0000-4000-8000-000000000008");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Evidence could not be displayed");
  await expect(page.getByText("Private projection failure")).toHaveCount(0);
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("status", { name: "Case status: completed" })).toBeVisible();
  await expect(page.locator("body")).not.toHaveAttribute("data-manual-test-invoked");
});
