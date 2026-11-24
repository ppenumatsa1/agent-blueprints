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
  expect(fetcher.mock.calls[0][1].redirect).toBe("error");
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
    .rejects.toThrow(new WorkflowClientError("You are not authorized for this record.", true));
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

it("uses bearer fetch for fragmented refresh signals without exposing event content", async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode("event: activity.ref"));
      controller.enqueue(encoder.encode("resh\ndata: {}\n\n: heartbeat\n\n"));
      controller.close();
    },
  });
  const fetcher = vi.fn().mockResolvedValue(new Response(body, {
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  }));
  vi.stubGlobal("fetch", fetcher);
  const refresh = vi.fn();
  await new HttpWorkflowClient(async () => "synthetic-token").activityStream(
    "80000000-0000-4000-8000-000000000008",
    new AbortController().signal,
    refresh,
  );
  expect(refresh).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer synthetic-token");
  expect(fetcher.mock.calls[0][1].credentials).toBe("omit");
  expect(fetcher.mock.calls[0][1].redirect).toBe("error");
});

it("reports revoked live access without reflecting server content", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private-canary", { status: 403 })));
  await expect(new HttpWorkflowClient(async () => "synthetic-token").activityStream(
    "80000000-0000-4000-8000-000000000008",
    new AbortController().signal,
    vi.fn(),
  )).rejects.toMatchObject({ authorizationFailure: true });
});

it("rejects malformed live events rather than silently losing refreshes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
    "event: activity.refresh\ndata: {\"private\":\"canary\"}\n\n",
    { headers: { "Content-Type": "text/event-stream" } },
  )));
  const refresh = vi.fn();
  await expect(new HttpWorkflowClient(async () => "synthetic-token").activityStream(
    "80000000-0000-4000-8000-000000000008",
    new AbortController().signal,
    refresh,
  )).rejects.toThrow("invalid response");
  expect(refresh).not.toHaveBeenCalled();
});

it("times out a stalled stream so the caller can reconnect", async () => {
  vi.useFakeTimers();
  try {
    const body = new ReadableStream<Uint8Array>({ start() {} });
    let signal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_path: string, options: RequestInit) => {
      signal = options.signal ?? undefined;
      return Promise.resolve(new Response(body, {
        headers: { "Content-Type": "text/event-stream" },
      }));
    }));
    const result = new HttpWorkflowClient(async () => "synthetic-token").activityStream(
      "80000000-0000-4000-8000-000000000008",
      new AbortController().signal,
      vi.fn(),
    );
    const rejected = expect(result).rejects.toThrow("timed out");
    await vi.advanceTimersByTimeAsync(20_001);
    await rejected;
    expect(signal?.aborted).toBe(true);
  } finally {
    vi.useRealTimers();
  }
});

it("cancels a stalled token acquisition without starting a fetch", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const controller = new AbortController();
  const client = new HttpWorkflowClient(() => new Promise<string>(() => {}));
  const operation = client.activityStream(
    "80000000-0000-4000-8000-000000000008",
    controller.signal,
    vi.fn(),
  );
  controller.abort();
  await expect(operation).rejects.toThrow("cancelled");
  expect(fetcher).not.toHaveBeenCalled();
});

it("cancels snapshot token acquisition and never sends a late fetch", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  let finish!: (token: string) => void;
  const client = new HttpWorkflowClient(() => new Promise<string>((resolve) => { finish = resolve; }));
  const controller = new AbortController();
  const operation = client.activity("80000000-0000-4000-8000-000000000008", {
    signal: controller.signal,
  });
  controller.abort();
  await expect(operation).rejects.toThrow("cancelled");
  finish("late-token");
  await Promise.resolve();
  expect(fetcher).not.toHaveBeenCalled();
});

it("times out a stalled token acquisition so live retry can continue", async () => {
  vi.useFakeTimers();
  try {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const client = new HttpWorkflowClient(() => new Promise<string>(() => {}));
    const operation = client.activityStream(
      "80000000-0000-4000-8000-000000000008",
      new AbortController().signal,
      vi.fn(),
    );
    const rejected = expect(operation).rejects.toThrow("timed out");
    await vi.advanceTimersByTimeAsync(15_001);
    await rejected;
    expect(fetcher).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});
