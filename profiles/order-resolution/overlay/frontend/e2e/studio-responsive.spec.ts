import { expect, test } from "@playwright/test";
import { createRequire } from "node:module";
import type { AxeResults } from "axe-core";

declare global {
  interface Window { axe: { run(): Promise<AxeResults> } }
}

const require = createRequire(import.meta.url);

test("synthetic launcher is accessible and responsive without executing a case", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/e2e/studio-fixture.html");
  await page.getByLabel("Synthetic use case").selectOption("ORS-001");
  await page.getByRole("button", { name: "Load use case" }).click();
  await expect(page.getByLabel("Order issue data (JSON)")).toHaveValue(/ORDER-LOW/);
  await expect(page.getByText(/Loading only prepares input/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  expect(await page.evaluate(async () => (await window.axe.run()).violations)).toEqual([]);
});
