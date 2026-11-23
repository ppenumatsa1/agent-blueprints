import { expect, test } from "@playwright/test";

test("generated frontend renders the real signed-out application in Chromium", async ({ page }) => {
  test.skip(process.env.E2E_LIVE === "true", "The local browser check is not a live deployment test.");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Workflow workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in to continue" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
  await expect(page.getByText("Configuration required")).toHaveCount(0);
});
