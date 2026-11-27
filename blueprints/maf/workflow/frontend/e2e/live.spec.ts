import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { authorizedOrigin, checkedStorageState, injectSessionStorage } from "./live-origin";

test("live generated frontend enforces separate owner and reviewer identities", async ({
  browser,
}) => {
  test.skip(process.env.E2E_LIVE !== "true", "Live browser E2E requires E2E_LIVE=true.");
  const required = [
    "E2E_BASE_URL",
    "E2E_AUTHORIZED_ORIGIN",
    "E2E_OWNER_STORAGE_STATE",
    "E2E_OWNER_SESSION_STORAGE",
    "E2E_REVIEWER_STORAGE_STATE",
    "E2E_REVIEWER_SESSION_STORAGE",
    "E2E_EXPECTED_TENANT_ID",
    "E2E_EXPECTED_SPA_CLIENT_ID",
    "E2E_EXPECTED_API_APP_ID_URI",
    "E2E_OWNER_ID",
    "E2E_REVIEWER_ID",
    "SOURCE_REVISION",
    "DEPLOYMENT_REVISION",
    "EVIDENCE_ENVIRONMENT",
  ] as const;
  for (const name of required) {
    expect(process.env[name], `${name} must be explicitly configured.`).toBeTruthy();
  }
  const origin = authorizedOrigin(process.env.E2E_BASE_URL!, process.env.E2E_AUTHORIZED_ORIGIN!);
  const payload = JSON.parse(
    process.env.E2E_PAYLOAD_JSON ?? '{"synthetic":true,"value":42}',
  ) as Record<string, unknown>;
  if (process.env.E2E_OWNER_ID === process.env.E2E_REVIEWER_ID) {
    throw new Error("Owner and reviewer must be distinct Entra object IDs.");
  }
  const loadSession = (name: "OWNER" | "REVIEWER") => {
    const entries = JSON.parse(
      readFileSync(process.env[`E2E_${name}_SESSION_STORAGE`]!, "utf8"),
    ) as Record<string, string>;
    if (
      !entries ||
      typeof entries !== "object" ||
      Array.isArray(entries) ||
      Object.values(entries).some((value) => typeof value !== "string")
    ) {
      throw new Error(`${name} session storage must be a JSON object of string values.`);
    }
    const serialized = JSON.stringify(entries);
    for (const expected of [
      "E2E_EXPECTED_TENANT_ID",
      "E2E_EXPECTED_SPA_CLIENT_ID",
      "E2E_EXPECTED_API_APP_ID_URI",
    ] as const) {
      if (!serialized.includes(process.env[expected]!)) {
        throw new Error(`${name} state does not match the explicit Entra configuration.`);
      }
    }
    return entries;
  };
  const context = async (name: "OWNER" | "REVIEWER") => {
    const result = await browser.newContext({
      baseURL: origin,
      storageState: checkedStorageState(
        JSON.parse(readFileSync(process.env[`E2E_${name}_STORAGE_STATE`]!, "utf8")) as unknown,
        origin,
      ),
    });
    await result.addInitScript(injectSessionStorage, { origin, entries: loadSession(name) });
    return result;
  };

  const ownerContext = await context("OWNER");
  const reviewerContext = await context("REVIEWER");
  try {
    const ownerPage = await ownerContext.newPage();
    await ownerPage.goto("/");
    await expect(ownerPage.getByRole("heading", { name: /^(New request|New order issue)$/ })).toBeVisible();
    await expect(ownerPage.getByRole("button", { name: "Sign in" })).toHaveCount(0);
    await ownerPage.getByLabel("Reviewer object ID").fill(process.env.E2E_REVIEWER_ID!);
    await ownerPage.getByLabel(/^(Request data|Order issue data) \(JSON\)$/).fill(JSON.stringify(payload));
    await ownerPage.getByRole("button", { name: /^(Submit request|Submit issue)$/ }).click();
    await expect(ownerPage.getByRole("status", { name: "Case status: pending" })).toBeVisible();
    await ownerPage.getByText("Open another case by ID").click();
    const recordId = await ownerPage.getByLabel("Case ID").inputValue();
    expect(recordId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );

    const reviewerPage = await reviewerContext.newPage();
    await reviewerPage.goto("/");
    await expect(reviewerPage.getByRole("button", { name: "Sign in" })).toHaveCount(0);
    await reviewerPage.getByText("Open a case").click();
    await reviewerPage.getByLabel("Case ID").fill(recordId);
    await reviewerPage.getByRole("button", { name: "Open" }).click();
    await expect(reviewerPage.getByRole("status", { name: "Case status: pending" })).toBeVisible();
    await reviewerPage.getByRole("button", { name: "Approve" }).click();
    await expect(reviewerPage.getByRole("status", { name: "Case status: completed" })).toBeVisible();
    await expect(reviewerPage.getByText("Decision: approved")).toBeVisible();

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
            "distinct explicit Entra owner and reviewer sessions loaded the deployed frontend",
            "the owner submitted a synthetic request through the protected API",
            "the assigned reviewer approved the pending request through the protected API",
          ],
        },
        null,
        2,
      )}\n`,
      { encoding: "utf8", mode: 0o600 },
    );
  } finally {
    await ownerContext.close();
    await reviewerContext.close();
  }
});
