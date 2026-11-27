import { act, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { HttpWorkflowClient } from "../api";
import { ActivityTimeline } from "../components/activity-timeline";
import { defaultWorkflowStudioProfile } from "../default-profile";

it("polls with authorization after stream 503s and clears activity on revocation", async () => {
  vi.useFakeTimers();
  try {
    let revoked = false;
    let updated = false;
    let reads = 0;
    let streams = 0;
    const fetcher = vi.fn((path: string, options: RequestInit) => {
      expect(options.headers).toMatchObject({ Authorization: "Bearer synthetic-token" });
      if (path.endsWith("/stream")) {
        streams += 1;
        return Promise.resolve(new Response("", { status: 503 }));
      }
      reads += 1;
      if (revoked) return Promise.resolve(new Response("", { status: 403 }));
      return Promise.resolve(new Response(JSON.stringify({
        schema_version: "workflow-activity/1",
        items: [
          { type: "created", created_at: "2026-01-02T03:04:05+00:00" },
          ...(updated ? [{ type: "action_failed", created_at: "2026-01-01T03:04:05+00:00" }] : []),
        ],
        next_cursor: null,
      }), { headers: { "Content-Type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetcher);
    const tokenFor = vi.fn().mockResolvedValue("synthetic-token");
    const { unmount } = render(
      <ActivityTimeline
        caseId="80000000-0000-4000-8000-000000000008"
        client={new HttpWorkflowClient(tokenFor)}
        profile={defaultWorkflowStudioProfile}
      />,
    );
    await act(async () => { await vi.advanceTimersByTimeAsync(7_000); });
    expect(streams).toBe(3);
    expect(reads).toBeGreaterThan(1);
    expect(screen.getByText("Workflow created")).toBeVisible();
    expect(screen.getByText("Activity shown may not include every workflow event.")).toBeVisible();
    expect(tokenFor.mock.calls.every(([scope]) => scope === "read")).toBe(true);

    updated = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(screen.getByText("Action failed")).toBeVisible();

    revoked = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.queryByText("Workflow created")).not.toBeInTheDocument();
    expect(screen.queryByText("Action failed")).not.toBeInTheDocument();
    const stoppedAt = reads;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(reads).toBe(stoppedAt);
    expect(streams).toBe(3);
    unmount();
  } finally {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  }
});
