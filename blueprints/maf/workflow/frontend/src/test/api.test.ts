import { afterEach, expect, it, vi } from "vitest";

import { HttpWorkflowClient, WorkflowClientError } from "../api";

afterEach(() => vi.unstubAllGlobals());

it("uses the requested delegated scope and sends the idempotency key", async () => {
  const tokenFor = vi.fn().mockResolvedValue("synthetic-access-token");
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      id: "id", correlation_id: "id", status: "pending", decision: "pending",
      payload: {}, execution_complete: false, failure_code: null,
    }),
  });
  vi.stubGlobal("fetch", fetcher);
  await new HttpWorkflowClient(tokenFor).submit("reviewer", {}, "request-key");
  expect(tokenFor).toHaveBeenCalledWith("write");
  expect(fetcher.mock.calls[0][1].headers).toMatchObject({
    Authorization: "Bearer synthetic-access-token",
    "Idempotency-Key": "request-key",
  });
  expect(fetcher.mock.calls[0][1].headers.traceparent)
    .toMatch(/^00-(?!0{32})[0-9a-f]{32}-(?!0{16})[0-9a-f]{16}-01$/);
});

it("continues without tracing when browser randomness is unavailable", async () => {
  vi.stubGlobal("crypto", { getRandomValues: () => { throw new Error("unavailable"); } });
  const fetcher = vi.fn().mockResolvedValue({ ok: false, status: 403 });
  vi.stubGlobal("fetch", fetcher);
  await expect(new HttpWorkflowClient(async () => "synthetic-token").read("id"))
    .rejects.toThrow("You are not authorized for this record.");
  expect(fetcher.mock.calls[0][1].headers.traceparent).toBeUndefined();
});

it("reports an authorization failure without reflecting the response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));
  await expect(new HttpWorkflowClient(async () => "synthetic-token").read("id"))
    .rejects.toThrow(new WorkflowClientError("You are not authorized for this record."));
});

it("uses the read scope and validates the versioned history response", async () => {
  const tokenFor = vi.fn().mockResolvedValue("synthetic-token");
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      schema_version: "workflow-history/1",
      items: [{
        id: "80000000-0000-4000-8000-000000000008",
        status: "pending",
        decision: "pending",
        created_at: "2026-01-01T00:00:00+00:00",
        updated_at: "2026-01-01T00:00:00+00:00",
      }],
      next_cursor: null,
    }),
  });
  vi.stubGlobal("fetch", fetcher);
  const page = await new HttpWorkflowClient(tokenFor).listHistory({ status: "pending", limit: 10 });
  expect(tokenFor).toHaveBeenCalledWith("read");
  expect(fetcher.mock.calls[0][0]).toBe("/api/cases?status=pending&limit=10");
  expect(page.items).toHaveLength(1);
});

it("rejects unknown activity events and unversioned history responses", async () => {
  const invalid = [
    { schema_version: "workflow-history/2", items: [], next_cursor: null },
    { schema_version: "workflow-activity/1", items: [{ type: "private_canary", created_at: "2026-01-01T00:00:00Z" }], next_cursor: null },
  ];
  for (const body of invalid) {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => body }));
    const client = new HttpWorkflowClient(async () => "synthetic-token");
    const operation = body.schema_version === "workflow-history/2"
      ? client.listHistory()
      : client.activity("80000000-0000-4000-8000-000000000008");
    await expect(operation).rejects.toThrow("invalid response");
  }
});
