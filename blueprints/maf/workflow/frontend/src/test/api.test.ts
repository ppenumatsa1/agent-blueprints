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
});

it("reports an authorization failure without reflecting the response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));
  await expect(new HttpWorkflowClient(async () => "synthetic-token").read("id"))
    .rejects.toThrow(new WorkflowClientError("You are not authorized for this record."));
});
