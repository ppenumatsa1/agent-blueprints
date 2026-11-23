import { expect, test } from "@playwright/test";

test("production-built studio shell renders the generic signed-out experience", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Workflow workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in to continue" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
  await expect(page.getByText(/order|refund|shipment|customer/i)).toHaveCount(0);
  await expect(page.getByText("Configuration required")).toHaveCount(0);
});
