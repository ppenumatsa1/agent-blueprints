import { expect, test } from "@playwright/test";

test("protocol context is opt-in, minimal, and removed on stop", async ({ page }) => {
  await page.goto("/e2e/protocol-context.html");
  await expect(page.getByLabel("Synthetic protocol consumer")).toHaveCount(0);
  await page.getByText("Open a case").click();
  await page.getByLabel("Case ID").fill("80000000-0000-4000-8000-000000000008");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.getByLabel("Synthetic protocol consumer")).toHaveCount(0);
  await page.getByRole("button", { name: "Share status with AG-UI" }).click();
  await expect(page.getByLabel("Synthetic protocol consumer")).toHaveText(
    '{"description":"Selected authorized case status","value":"{\\"status\\":\\"pending\\"}"}',
  );
  await expect(page.getByLabel("Synthetic protocol consumer")).not.toContainText("PRIVATE");
  await page.getByRole("button", { name: "Stop sharing with AG-UI" }).click();
  await expect(page.getByLabel("Synthetic protocol consumer")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
});
