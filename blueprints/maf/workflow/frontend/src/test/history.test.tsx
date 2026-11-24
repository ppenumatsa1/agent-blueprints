import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import { HttpWorkflowClient, WorkflowClientError, type WorkflowActivityPage, type WorkflowClient, type WorkflowHistoryPage } from "../api";
import { defaultWorkflowStudioProfile } from "../default-profile";
import { ActivityTimeline } from "../components/activity-timeline";
import { HistorySidebar } from "../components/history-sidebar";

const firstId = "80000000-0000-4000-8000-000000000008";
const secondId = "80000000-0000-4000-8000-000000000009";
const historyPage = (items: WorkflowHistoryPage["items"], next_cursor: string | null = null): WorkflowHistoryPage => ({
  schema_version: "workflow-history/1",
  items,
  next_cursor,
});
const activityPage = (
  type: WorkflowActivityPage["items"][number]["type"],
  next_cursor: string | null = null,
): WorkflowActivityPage => ({
  schema_version: "workflow-activity/1",
  items: [{ type, created_at: "2026-01-02T03:04:05+00:00" }],
  next_cursor,
});

function client(overrides: Partial<WorkflowClient> = {}): WorkflowClient {
  return {
    submit: vi.fn(),
    read: vi.fn(),
    decide: vi.fn(),
    listHistory: vi.fn().mockResolvedValue(historyPage([])),
    activity: vi.fn().mockResolvedValue({ schema_version: "workflow-activity/1", items: [], next_cursor: null }),
    ...overrides,
  };
}

const historyRecord = (id: string) => ({
  id,
  status: "pending" as const,
  decision: "pending" as const,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
});

describe("workflow history sidebar", () => {
  it("announces loading, reports empty results, and refreshes", async () => {
    let finishInitial!: (page: WorkflowHistoryPage) => void;
    const listHistory = vi.fn()
      .mockImplementationOnce(() => new Promise<WorkflowHistoryPage>((resolve) => { finishInitial = resolve; }))
      .mockResolvedValueOnce(historyPage([historyRecord(firstId)]));
    render(
      <HistorySidebar
        profile={defaultWorkflowStudioProfile}
        client={client({ listHistory })}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading history");
    finishInitial(historyPage([]));
    await screen.findByText("No workflows found.");
    await userEvent.click(screen.getByRole("button", { name: "Refresh history" }));
    expect(await screen.findByRole("button", { name: new RegExp(firstId) })).toBeVisible();
  });

  it("filters status, paginates, and selects only listed records", async () => {
    const onSelect = vi.fn();
    const listHistory = vi.fn()
      .mockResolvedValueOnce(historyPage([historyRecord(firstId)], "next"))
      .mockResolvedValueOnce(historyPage([historyRecord(firstId)], "next"))
      .mockResolvedValueOnce(historyPage([historyRecord(secondId)]));
    render(
      <HistorySidebar
        profile={defaultWorkflowStudioProfile}
        client={client({ listHistory })}
        selectedId={firstId}
        onSelect={onSelect}
      />,
    );
    const selected = await screen.findByRole("button", { name: new RegExp(firstId) });
    expect(selected).toHaveAttribute("aria-pressed", "true");
    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "pending");
    await waitFor(() => expect(listHistory).toHaveBeenLastCalledWith({ status: "pending", limit: 20 }));
    await userEvent.click(await screen.findByRole("button", { name: new RegExp(firstId) }));
    expect(onSelect).toHaveBeenCalledWith(firstId);
    await userEvent.click(screen.getByRole("button", { name: "Load more history" }));
    expect(await screen.findByRole("button", { name: new RegExp(secondId) })).toBeVisible();
  });

  it("resets load-more state when the status filter changes during pagination", async () => {
    let finishStalePage!: (page: WorkflowHistoryPage) => void;
    const listHistory = vi.fn()
      .mockResolvedValueOnce(historyPage([historyRecord(firstId)], "initial-cursor"))
      .mockImplementationOnce(
        () => new Promise<WorkflowHistoryPage>((resolve) => { finishStalePage = resolve; }),
      )
      .mockResolvedValueOnce(historyPage([historyRecord(secondId)], "new-filter-cursor"));
    const { container } = render(
      <HistorySidebar
        profile={defaultWorkflowStudioProfile}
        client={client({ listHistory })}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    await screen.findByRole("button", { name: new RegExp(firstId) });
    await userEvent.click(screen.getByRole("button", { name: "Load more history" }));
    expect(screen.getByRole("button", { name: "Loading history..." })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "pending");
    await screen.findByRole("button", { name: new RegExp(secondId) });
    expect(screen.getByRole("button", { name: "Load more history" })).toBeEnabled();
    await waitFor(() => expect(container.querySelector("aside")).toHaveAttribute("aria-busy", "false"));

    finishStalePage(historyPage([historyRecord(firstId)]));
    await waitFor(() => expect(container.querySelector("aside")).toHaveAttribute("aria-busy", "false"));
    expect(screen.getByRole("button", { name: "Load more history" })).toBeEnabled();
  });

  it("exposes a safe error state and has no accessibility violations", async () => {
    const api = client({ listHistory: vi.fn().mockRejectedValue(new Error("private canary")) });
    const { container } = render(
      <HistorySidebar
        profile={defaultWorkflowStudioProfile}
        client={api}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Workflow history could not be loaded.");
    expect(screen.queryByText("private canary")).not.toBeInTheDocument();

    const empty = client();
    const mounted = render(
      <ActivityTimeline caseId={firstId} client={empty} profile={defaultWorkflowStudioProfile} />,
    );
    await screen.findByText("No workflows found.");
    const result = await axe.run(mounted.container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations).toEqual([]);
    mounted.unmount();
    expect(container.querySelector("aside")).toBeInTheDocument();
  });
});

describe("workflow activity timeline", () => {
  it("does not start a stream when the profile disables live activity", async () => {
    const activityStream = vi.fn();
    const profile = {
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, liveActivity: false },
    };
    render(
      <ActivityTimeline caseId={firstId} client={client({ activityStream })} profile={profile} />,
    );
    await screen.findByText("No workflows found.");
    expect(activityStream).not.toHaveBeenCalled();
  });

  it("reconciles all pages when an older event commits later", async () => {
    let refresh!: () => void;
    const activity = vi.fn()
      .mockResolvedValueOnce(activityPage("created"))
      .mockResolvedValueOnce({ ...activityPage("created"), next_cursor: "older" })
      .mockResolvedValueOnce(activityPage("action_failed"));
    const api = client({
      activity,
      activityStream: vi.fn((_id, _signal, callback) => {
        refresh = callback;
        return new Promise<void>(() => {});
      }),
    });
    render(<ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />);
    await screen.findByText("Workflow created");
    act(() => refresh());
    await screen.findByText("Action failed");
    expect(activity.mock.calls[2][1]).toMatchObject({ cursor: "older", limit: 100 });
  });

  it("reports a nonadvancing snapshot cursor rather than showing a truncated result", async () => {
    let refresh!: () => void;
    const activity = vi.fn()
      .mockResolvedValueOnce(activityPage("created"))
      .mockResolvedValue({ ...activityPage("created"), next_cursor: "repeat" });
    const api = client({
      activity,
      activityStream: vi.fn((_id, _signal, callback) => {
        refresh = callback;
        return new Promise<void>(() => {});
      }),
    });
    render(<ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />);
    await screen.findByText("Workflow created");
    act(() => refresh());
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.queryByText("Workflow created")).not.toBeInTheDocument();
  });

  it("reports an oversized snapshot without silently truncating it", async () => {
    let refresh!: () => void;
    let page = 0;
    const activity = vi.fn()
      .mockResolvedValueOnce(activityPage("created"))
      .mockImplementation(async () => ({
        ...activityPage("created"),
        next_cursor: `page-${++page}`,
      }));
    const api = client({
      activity,
      activityStream: vi.fn((_id, _signal, callback) => {
        refresh = callback;
        return new Promise<void>(() => {});
      }),
    });
    render(<ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />);
    await screen.findByText("Workflow created");
    act(() => refresh());
    expect(await screen.findByRole("alert")).toHaveTextContent("exceeds the reconciliation limits");
    expect(activity).toHaveBeenCalledTimes(51);
    expect(screen.queryByText("Workflow created")).not.toBeInTheDocument();
  });

  it("coalesces refresh bursts into at most one scan per 15 seconds", async () => {
    vi.useFakeTimers();
    try {
      let refresh!: () => void;
      const activity = vi.fn().mockResolvedValue(activityPage("created"));
      const api = client({
        activity,
        activityStream: vi.fn((_id, _signal, callback) => {
          refresh = callback;
          return new Promise<void>(() => {});
        }),
      });
      const { unmount } = render(
        <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
      );
      await act(async () => { await Promise.resolve(); });
      await act(async () => { refresh(); await Promise.resolve(); });
      expect(activity).toHaveBeenCalledTimes(2);
      await act(async () => { refresh(); refresh(); await vi.advanceTimersByTimeAsync(14_999); });
      expect(activity).toHaveBeenCalledTimes(2);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      expect(activity).toHaveBeenCalledTimes(3);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("reconciles an older late commit and replaces replayed snapshots without duplication", async () => {
    let refresh!: () => void;
    const activity = vi.fn()
      .mockResolvedValueOnce(activityPage("created"))
      .mockResolvedValue({
        schema_version: "workflow-activity/1",
        items: [
          { type: "created", created_at: "2026-01-02T03:04:05+00:00" },
          { type: "action_failed", created_at: "2026-01-01T03:04:05+00:00" },
        ],
        next_cursor: null,
      });
    const api = client({
      activity,
      activityStream: vi.fn((_id, _signal, callback) => {
        refresh = callback;
        return new Promise<void>(() => {});
      }),
    });
    render(<ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />);
    await screen.findByText("Workflow created");
    act(() => refresh());
    await screen.findByText("Action failed");
    act(() => refresh());
    expect(activity).toHaveBeenCalledTimes(2);
    expect(screen.getAllByText("Action failed")).toHaveLength(1);
    expect(screen.getAllByText("Workflow created")).toHaveLength(1);
  });

  it("aborts live activity and in-flight reads when the case changes", async () => {
    const signals: AbortSignal[] = [];
    const activity = vi.fn().mockResolvedValue(activityPage("created"));
    const api = client({
      activity,
      activityStream: vi.fn((_id, signal) => {
        signals.push(signal);
        return new Promise<void>(() => {});
      }),
    });
    const { rerender, unmount } = render(
      <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
    );
    await screen.findByText("Workflow created");
    const firstRead = activity.mock.calls[0][1].signal as AbortSignal;
    rerender(<ActivityTimeline caseId={secondId} client={api} profile={defaultWorkflowStudioProfile} />);
    expect(signals[0].aborted).toBe(true);
    expect(firstRead.aborted).toBe(true);
    await waitFor(() => expect(signals).toHaveLength(2));
    unmount();
    expect(signals[1].aborted).toBe(true);
  });

  it("clears the snapshot when access is revoked", async () => {
    let fail!: (reason: Error) => void;
    const api = client({
      activity: vi.fn().mockResolvedValue(activityPage("created")),
      activityStream: vi.fn(() => new Promise<void>((_resolve, reject) => { fail = reject; })),
    });
    render(<ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />);
    await screen.findByText("Workflow created");
    await act(async () => fail(new WorkflowClientError("revoked", true)));
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.queryByText("Workflow created")).not.toBeInTheDocument();
  });

  it("falls back to authorized snapshot polling after bounded reconnects", async () => {
    vi.useFakeTimers();
    try {
      const activity = vi.fn().mockResolvedValue(activityPage("created"));
      const activityStream = vi.fn().mockRejectedValue(new Error("network"));
      const api = client({ activity, activityStream });
      const { unmount } = render(
        <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
      );
      await act(async () => { await Promise.resolve(); });
      await act(async () => { await vi.advanceTimersByTimeAsync(7_000); });
      expect(activityStream).toHaveBeenCalledTimes(3);
      expect(activity.mock.calls.length).toBeGreaterThan(1);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses authorized polling when the client has no stream implementation", async () => {
    vi.useFakeTimers();
    try {
      const activity = vi.fn().mockResolvedValue(activityPage("created"));
      const { unmount } = render(
        <ActivityTimeline caseId={firstId} client={client({ activity })} profile={defaultWorkflowStudioProfile} />,
      );
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(activity.mock.calls.length).toBeGreaterThan(1);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("renews healthy finite streams without exhausting the failure budget", async () => {
    vi.useFakeTimers();
    try {
      const activityStream = vi.fn(async (_id: string, _signal: AbortSignal, refresh: () => void) => {
        refresh();
        await new Promise<void>((resolve) => setTimeout(resolve, 30_000));
      });
      const api = client({ activityStream });
      const { unmount } = render(
        <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
      );
      await act(async () => { await vi.advanceTimersByTimeAsync(125_000); });
      expect(activityStream.mock.calls.length).toBeGreaterThanOrEqual(4);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("falls back after short streams that refresh and then fail", async () => {
    vi.useFakeTimers();
    try {
      const activityStream = vi.fn(async (_id: string, _signal: AbortSignal, refresh: () => void) => {
        refresh();
        throw new Error("abrupt disconnect");
      });
      const activity = vi.fn().mockResolvedValue(activityPage("created"));
      const api = client({ activity, activityStream });
      const { unmount } = render(
        <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
      );
      await act(async () => { await vi.advanceTimersByTimeAsync(25_000); });
      expect(activityStream).toHaveBeenCalledTimes(3);
      expect(activity.mock.calls.length).toBeGreaterThan(1);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("aborts stalled HTTP-200 streams and eventually falls back to polling", async () => {
    vi.useFakeTimers();
    try {
      const signals: AbortSignal[] = [];
      let reads = 0;
      vi.stubGlobal("fetch", vi.fn((path: string, options: RequestInit) => {
        if (path.endsWith("/stream")) {
          signals.push(options.signal as AbortSignal);
          return Promise.resolve(new Response(new ReadableStream<Uint8Array>({ start() {} }), {
            headers: { "Content-Type": "text/event-stream" },
          }));
        }
        reads += 1;
        return Promise.resolve(new Response(JSON.stringify(activityPage("created")), {
          headers: { "Content-Type": "application/json" },
        }));
      }));
      const api = new HttpWorkflowClient(async () => "synthetic-token");
      const { unmount } = render(
        <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
      );
      await act(async () => { await vi.advanceTimersByTimeAsync(80_000); });
      expect(signals).toHaveLength(3);
      expect(signals.every((signal) => signal.aborted)).toBe(true);
      expect(reads).toBeGreaterThan(1);
      unmount();
    } finally {
      vi.useRealTimers();
      vi.unstubAllGlobals();
    }
  });

  it("discards a late response for a stale selection", async () => {
    let finishOld!: (page: WorkflowActivityPage) => void;
    const api = client({
      activity: vi.fn()
        .mockReturnValueOnce(new Promise<WorkflowActivityPage>((resolve) => { finishOld = resolve; }))
        .mockResolvedValueOnce(activityPage("decision_recorded")),
    });
    const { rerender } = render(
      <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
    );
    rerender(
      <ActivityTimeline caseId={secondId} client={api} profile={defaultWorkflowStudioProfile} />,
    );
    expect(await screen.findByText("Decision recorded")).toBeVisible();
    finishOld(activityPage("action_failed"));
    await waitFor(() => expect(screen.queryByText("Action failed")).not.toBeInTheDocument());
  });

  it("resets load-more state when the selected case changes during pagination", async () => {
    let finishStalePage!: (page: WorkflowActivityPage) => void;
    const api = client({
      activity: vi.fn()
        .mockReturnValueOnce(Promise.resolve(activityPage("created", "initial-cursor")))
        .mockReturnValueOnce(
          new Promise<WorkflowActivityPage>((resolve) => { finishStalePage = resolve; }),
        )
        .mockReturnValueOnce(Promise.resolve(activityPage("decision_recorded", "case-cursor"))),
    });
    const { container, rerender } = render(
      <ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />,
    );
    await screen.findByText("Workflow created");
    await userEvent.click(screen.getByRole("button", { name: "Load more history" }));
    expect(screen.getByRole("button", { name: "Loading history..." })).toBeDisabled();
    rerender(
      <ActivityTimeline caseId={secondId} client={api} profile={defaultWorkflowStudioProfile} />,
    );
    await screen.findByText("Decision recorded");
    expect(screen.getByRole("button", { name: "Load more history" })).toBeEnabled();
    await waitFor(() =>
      expect(container.querySelector(".activity-timeline")).toHaveAttribute("aria-busy", "false"),
    );

    finishStalePage(activityPage("action_failed"));
    await waitFor(() =>
      expect(container.querySelector(".activity-timeline")).toHaveAttribute("aria-busy", "false"),
    );
    expect(screen.queryByText("Action failed")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load more history" })).toBeEnabled();
  });

  it("shows loading, empty, refresh, and safe error states", async () => {
    const activity = vi.fn()
      .mockResolvedValueOnce({ schema_version: "workflow-activity/1", items: [], next_cursor: null })
      .mockResolvedValueOnce(activityPage("created"))
      .mockRejectedValueOnce(new Error("private canary"));
    const api = client({ activity });
    render(<ActivityTimeline caseId={firstId} client={api} profile={defaultWorkflowStudioProfile} />);
    await screen.findByText("No workflows found.");
    await userEvent.click(screen.getByRole("button", { name: "Refresh activity" }));
    expect(await screen.findByText("Workflow created")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Refresh activity" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Workflow history could not be loaded.");
    expect(screen.queryByText("private canary")).not.toBeInTheDocument();
  });
});
