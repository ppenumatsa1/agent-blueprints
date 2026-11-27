import { expect, test } from "@playwright/test";

test("history selection opens the accessible record activity timeline", async ({ page }) => {
  await page.goto("/e2e/history.html");
  await expect(page.getByRole("heading", { name: "Workflow history" })).toBeVisible();
  await page.getByLabel("Filter by status").selectOption("pending");
  const record = page.getByRole("button", { name: /80000000-0000-4000-8000-000000000008/ });
  await expect(record).toBeVisible();
  await record.click();
  await expect(page.getByRole("heading", { name: "Event Timeline" })).toBeVisible();
  await expect(page.getByText("Workflow created")).toBeVisible();
  await expect(page.getByText(/Activity may not include every workflow event/)).toBeVisible();
});
