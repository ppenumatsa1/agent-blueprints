import { expect, test } from "@playwright/test";

test("production-built Order Resolution studio renders the signed-out experience", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Order Resolution" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in to continue" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Submit issue" })).toHaveCount(0);
  await expect(page.getByText(/refund|shipment|customer/i)).toHaveCount(0);
  await expect(page.getByText("Configuration required")).toHaveCount(0);
});
