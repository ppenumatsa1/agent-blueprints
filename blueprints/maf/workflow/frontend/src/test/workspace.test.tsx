import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowClientError, type WorkflowCase, type WorkflowClient } from "../api";
import { defaultWorkflowStudioProfile } from "../default-profile";
import { WorkflowWorkspace } from "../workspace";

const reviewer = "40000000-0000-4000-8000-000000000004";
const id = "80000000-0000-4000-8000-000000000008";
const pending: WorkflowCase = {
  id,
  correlation_id: id,
  status: "pending",
  decision: "pending",
  payload: { summary: "Synthetic request" },
  execution_complete: false,
  failure_code: null,
};

function client(overrides: Partial<WorkflowClient> = {}): WorkflowClient {
  return {
    submit: vi.fn().mockResolvedValue(pending),
    read: vi.fn().mockResolvedValue(pending),
    listHistory: vi.fn().mockResolvedValue({
      schema_version: "workflow-history/1" as const,
      items: [],
      next_cursor: null,
    }),
    activity: vi.fn().mockResolvedValue({
      schema_version: "workflow-activity/1" as const,
      items: [],
      next_cursor: null,
    }),
    decide: vi.fn().mockResolvedValue({ ...pending, status: "completed", decision: "approved", execution_complete: true }),
    ...overrides,
  };
}

function workspace(api: WorkflowClient, signedIn = true) {
  return (
    <WorkflowWorkspace
      signedIn={signedIn}
      client={api}
      profile={defaultWorkflowStudioProfile}
      signIn={vi.fn().mockResolvedValue(undefined)}
      signOut={vi.fn().mockResolvedValue(undefined)}
    />
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("workflow workspace", () => {
  it("shows a sign-in state without exposing request controls", async () => {
    const signIn = vi.fn().mockResolvedValue(undefined);
    render(
      <WorkflowWorkspace
        signedIn={false}
        client={client()}
        profile={defaultWorkflowStudioProfile}
        signIn={signIn}
        signOut={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: /sign in to continue/i })).toBeVisible();
    expect(screen.queryByLabelText(/reviewer object id/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(signIn).toHaveBeenCalledOnce();
  });

  it("shows loading, a pending request, and the approved outcome", async () => {
    let finish!: (value: WorkflowCase) => void;
    const submit = vi.fn().mockReturnValue(new Promise<WorkflowCase>((resolve) => { finish = resolve; }));
    const api = client({ submit });
    render(workspace(api));
    await userEvent.type(screen.getByLabelText("Reviewer object ID"), reviewer);
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(screen.getByRole("status")).toHaveTextContent("Working");
    expect(screen.getByRole("button", { name: "Submit request" })).toBeDisabled();
    finish(pending);
    expect(await screen.findByRole("heading", { name: "Case status: pending" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("heading", { name: "Case status: completed" })).toBeVisible();
    expect(api.decide).toHaveBeenCalledWith(id, "approved");
  });

  it("refreshes asynchronous submissions until completion", async () => {
    vi.useFakeTimers();
    try {
      const created = { ...pending, status: "created" as const };
      const complete = { ...pending, status: "completed" as const, decision: "approved" as const, execution_complete: true };
      const api = client({
        submit: vi.fn().mockResolvedValue(created),
        read: vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(complete),
      });

      const { unmount } = render(workspace(api));
      fireEvent.change(screen.getByLabelText("Reviewer object ID"), { target: { value: reviewer } });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Submit request" })); });
      expect(screen.getByRole("heading", { name: "Case status: created" })).toBeVisible();
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(screen.getByRole("heading", { name: "Case status: pending" })).toBeVisible();
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(screen.getByRole("heading", { name: "Case status: completed" })).toBeVisible();
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(api.read).toHaveBeenCalledTimes(2);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("retries a transient refresh failure and clears its alert after recovery", async () => {
    vi.useFakeTimers();
    try {
      const complete = { ...pending, status: "completed" as const, execution_complete: true };
      const read = vi.fn().mockResolvedValueOnce(pending)
        .mockRejectedValueOnce(new WorkflowClientError("Refresh unavailable."))
        .mockResolvedValueOnce(complete);
      const { unmount } = render(workspace(client({ read })));
      fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: id } });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open" })); });
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(screen.getByRole("alert")).toHaveTextContent("Refresh unavailable.");
      expect(screen.getByRole("heading", { name: "Case status: pending" })).toBeVisible();
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(screen.getByRole("heading", { name: "Case status: completed" })).toBeVisible();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(read).toHaveBeenCalledTimes(3);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("refreshes a failed nonterminal case until hosted completion", async () => {
    vi.useFakeTimers();
    try {
      const failed = { ...pending, failure_code: "hosted_response_failed" };
      const complete = { ...failed, status: "completed" as const, decision: "approved" as const, execution_complete: true, failure_code: null };
      const read = vi.fn().mockResolvedValueOnce(failed).mockResolvedValueOnce(complete);
      const { unmount } = render(workspace(client({ read })));
      fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: id } });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open" })); });
      expect(screen.getByText(/recovery or action failed/i)).toBeVisible();
      expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(screen.getByRole("heading", { name: "Case status: completed" })).toBeVisible();
      expect(screen.queryByText(/recovery or action failed/i)).not.toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(read).toHaveBeenCalledTimes(2);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("aborts a stalled refresh and resumes polling", async () => {
    vi.useFakeTimers();
    try {
      const complete = { ...pending, status: "completed" as const, execution_complete: true };
      let stalledSignal: AbortSignal | undefined;
      const read = vi.fn().mockResolvedValueOnce(pending)
        .mockImplementationOnce((_id, options) => {
          stalledSignal = options.signal;
          return new Promise<WorkflowCase>(() => {});
        })
        .mockResolvedValueOnce(complete);
      const { unmount } = render(workspace(client({ read })));
      fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: id } });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open" })); });
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(stalledSignal?.aborted).toBe(false);
      await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
      expect(stalledSignal?.aborted).toBe(true);
      expect(screen.getByRole("alert")).toHaveTextContent("Case refresh timed out.");
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(screen.getByRole("heading", { name: "Case status: completed" })).toBeVisible();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("discards a stale refresh when another case is opened", async () => {
        vi.useFakeTimers();
        try {
          const other = { ...pending, id: "90000000-0000-4000-8000-000000000009" };
          let finish!: (value: WorkflowCase) => void;
          const read = vi.fn()
            .mockResolvedValueOnce(pending)
            .mockReturnValueOnce(new Promise<WorkflowCase>((resolve) => { finish = resolve; }))
            .mockResolvedValueOnce(other);
          const { unmount } = render(workspace(client({ read })));
          fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: id } });
          await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open" })); });
          await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
          fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: other.id } });
          await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open" })); });
          await act(async () => { finish({ ...pending, status: "completed", execution_complete: true }); });
          expect(screen.getByText(other.id)).toBeVisible();
          expect(screen.getByRole("heading", { name: "Case status: pending" })).toBeVisible();
          unmount();
        } finally {
          vi.useRealTimers();
        }
      });

      it("clears the case and stops refreshing when read access is revoked", async () => {
        vi.useFakeTimers();
        try {
          const read = vi.fn().mockResolvedValueOnce(pending)
            .mockRejectedValueOnce(new WorkflowClientError("Access revoked.", true));
          const { unmount } = render(workspace(client({ read })));
          fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: id } });
          await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open" })); });
          await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
          expect(screen.getByRole("alert")).toHaveTextContent("Access revoked.");
          expect(screen.queryByRole("heading", { name: "Case status: pending" })).not.toBeInTheDocument();
          await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
          expect(read).toHaveBeenCalledTimes(2);
          unmount();
        } finally {
          vi.useRealTimers();
        }
      });
  it("opens a record and displays rejection", async () => {
    const api = client({
      decide: vi.fn().mockResolvedValue({ ...pending, status: "rejected", decision: "rejected", execution_complete: true }),
    });
    render(workspace(api));
    await userEvent.type(screen.getByLabelText("Case ID"), id);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await screen.findByRole("heading", { name: "Case status: pending" });
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(await screen.findByRole("heading", { name: "Case status: rejected" })).toBeVisible();
    expect(api.decide).toHaveBeenCalledWith(id, "rejected");
  });

  it("retains the idempotency key after a failed submission", async () => {
    const submit = vi.fn()
      .mockRejectedValueOnce(new WorkflowClientError("The service could not be reached."))
      .mockResolvedValueOnce(pending);
    render(workspace(client({ submit })));
    await userEvent.type(screen.getByLabelText("Reviewer object ID"), reviewer);
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be reached");
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    await screen.findByRole("heading", { name: "Case status: pending" });
    expect(submit.mock.calls[0][2]).toBe(submit.mock.calls[1][2]);
  });

  it("reports invalid input and exposes accessible form controls", async () => {
    const { container } = render(workspace(client()));
    await userEvent.type(screen.getByLabelText("Reviewer object ID"), "not-a-uuid");
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reviewer object ID");
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    await waitFor(() => expect(result.violations).toEqual([]));
  });

  it("shows recovery and failure states without enabling later-layer capabilities", async () => {
    const recovering = {
      ...pending,
      status: "completed" as const,
      failure_code: "synthetic_failure",
    };
    render(workspace(client({ read: vi.fn().mockResolvedValue(recovering) })));
    await userEvent.type(screen.getByLabelText("Case ID"), id);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByRole("heading", { name: "Case status: recovering" })).toBeVisible();
    expect(screen.getByText(/recovery or action failed/i)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Workflow history" })).toBeVisible();
    expect(screen.getByText("Live activity: Enabled")).toBeVisible();
    expect(screen.getByText("Evidence: Not enabled")).toBeVisible();
    expect(screen.getByText("Manual tests: Not enabled")).toBeVisible();
    expect(screen.getByText("AG-UI: Not enabled")).toBeVisible();
    expect(screen.getByText("CopilotKit: Not enabled")).toBeVisible();
  });

  it.each(["hosted_response_failed", "recovery_failed"])("does not offer decisions for a pending case with %s", async (failure_code) => {
    const failed = { ...pending, failure_code };
    render(workspace(client({ read: vi.fn().mockResolvedValue(failed) })));
    await userEvent.type(screen.getByLabelText("Case ID"), id);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByText(/recovery or action failed/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });
});
