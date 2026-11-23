import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowActivityPage, WorkflowClient, WorkflowHistoryPage } from "../api";
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
