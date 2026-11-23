import { render, screen, waitFor } from "@testing-library/react";
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
    expect(screen.getByText("History: Not enabled")).toBeVisible();
    expect(screen.getByText("Live activity: Not enabled")).toBeVisible();
    expect(screen.getByText("Evidence: Not enabled")).toBeVisible();
    expect(screen.getByText("Manual tests: Not enabled")).toBeVisible();
    expect(screen.getByText("AG-UI: Not enabled")).toBeVisible();
    expect(screen.getByText("CopilotKit: Not enabled")).toBeVisible();
  });
});
