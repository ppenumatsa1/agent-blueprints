import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

test("live generated frontend persists and approves a synthetic request", async ({ page }) => {
  test.skip(process.env.E2E_LIVE !== "true", "Live browser E2E requires E2E_LIVE=true.");
  const required = [
    "E2E_BASE_URL",
    "E2E_STORAGE_STATE",
    "E2E_SESSION_STORAGE",
    "E2E_EXPECTED_TENANT_ID",
    "E2E_EXPECTED_SPA_CLIENT_ID",
    "E2E_EXPECTED_API_APP_ID_URI",
    "E2E_REVIEWER_ID",
    "SOURCE_REVISION",
    "DEPLOYMENT_REVISION",
    "EVIDENCE_ENVIRONMENT",
  ] as const;
  for (const name of required) {
    expect(process.env[name], `${name} must be explicitly configured.`).toBeTruthy();
  }
  const payload = JSON.parse(
    process.env.E2E_PAYLOAD_JSON ?? '{"synthetic":true,"value":42}',
  ) as Record<string, unknown>;
  const sessionEntries = JSON.parse(
    readFileSync(process.env.E2E_SESSION_STORAGE!, "utf8"),
  ) as Record<string, string>;
  if (
    !sessionEntries ||
    Array.isArray(sessionEntries) ||
    Object.values(sessionEntries).some((value) => typeof value !== "string")
  ) {
    throw new Error("E2E session storage must be a JSON object of string values.");
  }
  const serializedSession = JSON.stringify(sessionEntries);
  for (const name of [
    "E2E_EXPECTED_TENANT_ID",
    "E2E_EXPECTED_SPA_CLIENT_ID",
    "E2E_EXPECTED_API_APP_ID_URI",
  ] as const) {
    if (!serializedSession.includes(process.env[name]!)) {
      throw new Error("Authenticated state does not match the explicit Entra configuration.");
    }
  }
  await page.addInitScript((entries) => {
    for (const [key, value] of Object.entries(entries)) {
      window.sessionStorage.setItem(key, value);
    }
  }, sessionEntries);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "New request" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toHaveCount(0);
  await page.getByLabel("Reviewer object ID").fill(process.env.E2E_REVIEWER_ID!);
  await page.getByLabel("Request data (JSON)").fill(JSON.stringify(payload));
  await page.getByRole("button", { name: "Submit request" }).click();
  await expect(page.getByRole("heading", { name: "Record status: pending" })).toBeVisible();
  const recordId = (await page.getByText(/^Record ID:/).textContent())?.replace("Record ID: ", "");
  expect(recordId).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  );
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("heading", { name: "Record status: completed" })).toBeVisible();
  await expect(page.getByText("Decision: approved")).toBeVisible();

  const output = resolve(
    process.env.E2E_EVIDENCE_FILE ?? "test-results/live-browser-evidence.json",
  );
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(
    output,
    `${JSON.stringify(
      {
        schema_version: "1.0.0",
        source_revision: process.env.SOURCE_REVISION,
        deployment_revision: process.env.DEPLOYMENT_REVISION,
        environment: process.env.EVIDENCE_ENVIRONMENT,
        recorded_at: new Date().toISOString(),
        check_id: "BROWSER-E2E",
        outcome: "passed",
        record_id: recordId,
        assertions: [
          "explicit Entra session loaded the deployed authenticated frontend",
          "synthetic request reached pending approval through the protected API",
          "approval completed through the live API",
        ],
      },
      null,
      2,
    )}\n`,
    { encoding: "utf8", mode: 0o600 },
  );
});
