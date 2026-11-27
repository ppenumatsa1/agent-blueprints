import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowCase, WorkflowClient } from "../api";
import { orderResolutionProfile } from "../order-resolution";
import { WorkflowWorkspace } from "../workspace";


describe("order resolution case", () => {
  function revealCaseLookup() {
    const disclosure = document.querySelector<HTMLDetailsElement>(".case-lookup");
    if (disclosure && !disclosure.open) {
      const summary = disclosure.querySelector("summary");
      if (summary) fireEvent.click(summary);
    }
  }

  it("exposes the live browser controls and case ID for the profile", async () => {
    const id = "80000000-0000-4000-8000-000000000008";
    const pending: WorkflowCase = {
      id, correlation_id: id, status: "pending", decision: "pending",
      payload: { proposal: { version: 1, action: "manual_review", destination_id: "synthetic", approval_required: true } },
      decision_handle: "opaque-handle", decision_channel: "foundry-responses",
      execution_complete: false, failure_code: null,
    };
    const client: WorkflowClient = {
      submit: vi.fn().mockResolvedValue(pending),
      read: vi.fn().mockResolvedValue(pending),
      decide: vi.fn().mockResolvedValue({
        ...pending, status: "completed", decision: "approved", execution_complete: true,
      }),
      listHistory: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
      activity: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    };
    render(
      <WorkflowWorkspace
        signedIn
        client={client}
        profile={orderResolutionProfile}
        signIn={vi.fn()}
        signOut={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: /^(New request|New order issue)$/ })).toBeVisible();
    await userEvent.type(screen.getByLabelText("Reviewer object ID"), id);
    await userEvent.click(screen.getByText("Advanced: edit request JSON"));
    expect(screen.getByLabelText(/^(Request data|Order issue data) \(JSON\)$/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /^(Submit request|Submit issue)$/ }));
    expect(await screen.findByRole("status", { name: "Case status: pending" })).toBeVisible();
    await userEvent.click(screen.getByText("Open another case by ID"));
    expect(screen.getByLabelText("Case ID")).toHaveValue(id);
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("status", { name: "Case status: completed" })).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Approval" })).getByText("Decision:"))
      .toHaveTextContent("Decision: approved");
  });

  it("renders the deterministic proposal and rejection status", () => {
    const record: WorkflowCase = {
      id: "80000000-0000-4000-8000-000000000008",
      correlation_id: "80000000-0000-4000-8000-000000000008",
      status: "rejected",
      decision: "rejected",
      payload: {
        order: { id: "ORDER-HIGH", issue: "late_delivery" },
        proposal: {
          action: "partial_refund_10",
          amount: "18.50",
          currency: "USD",
          approval_required: true,
        },
      },
      execution_complete: true,
      failure_code: null,
    };
    expect(orderResolutionProfile.projectPayload(record.payload, record)).toEqual({
      summary: "Review partial_refund_10 for ORDER-HIGH.",
      fields: [
        { label: "Order", value: "ORDER-HIGH" },
        { label: "Issue", value: "late_delivery" },
        { label: "Proposed action", value: "partial_refund_10" },
        { label: "Proposed amount", value: "USD 18.50" },
        { label: "Approval required", value: "Yes" },
        { label: "Status", value: "rejected" },
      ],
    });
  });

  it("binds an approval decision to the exact proposal and server handle", () => {
    const record: WorkflowCase = {
      id: "80000000-0000-4000-8000-000000000008",
      correlation_id: "80000000-0000-4000-8000-000000000008",
      status: "pending",
      decision: "pending",
      payload: {
        proposal: {
          version: 3,
          action: "manual_review",
          destination_id: "synthetic-destination",
        },
      },
      decision_handle: "opaque-handle",
      decision_channel: "foundry-responses",
      execution_complete: false,
      failure_code: null,
    };
    expect(orderResolutionProfile.decisionBinding?.(record)).toEqual({
      proposal_version: 3,
      action: "manual_review",
      destination_id: "synthetic-destination",
      handle: "opaque-handle",
      channel: "foundry-responses",
    });
    expect(orderResolutionProfile.decisionBinding?.({ ...record, decision_channel: "api" })?.channel).toBe("api");
    expect(orderResolutionProfile.decisionBinding?.({ ...record, decision_channel: null })).toBeUndefined();
  });

  it.each(["approved", "rejected"] as const)("sends the hosted binding for %s", async (decision) => {
    const record: WorkflowCase = {
      id: "80000000-0000-4000-8000-000000000008",
      correlation_id: "80000000-0000-4000-8000-000000000008",
      status: "pending",
      decision: "pending",
      payload: { proposal: { version: 3, action: "manual_review", destination_id: "synthetic", approval_required: true } },
      decision_handle: "opaque-handle",
      decision_channel: "foundry-responses",
      execution_complete: false,
      failure_code: null,
    };
    const client: WorkflowClient = {
      submit: vi.fn(),
      read: vi.fn().mockResolvedValue(record),
      decide: vi.fn().mockResolvedValue({ ...record, status: decision, decision, execution_complete: true }),
      listHistory: vi.fn().mockResolvedValue({ schema_version: "workflow-history/1", items: [], next_cursor: null }),
      activity: vi.fn().mockResolvedValue({ schema_version: "workflow-activity/1", items: [], next_cursor: null }),
    };
    render(<WorkflowWorkspace signedIn client={client} profile={orderResolutionProfile} signIn={vi.fn()} signOut={vi.fn()} />);
    revealCaseLookup();
    fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: record.id } });
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    fireEvent.click(await screen.findByRole("button", { name: decision === "approved" ? "Approve" : "Reject" }));
    await waitFor(() => expect(client.decide).toHaveBeenCalledWith(record.id, decision, {
      proposal_version: 3,
      action: "manual_review",
      destination_id: "synthetic",
      handle: "opaque-handle",
      channel: "foundry-responses",
    }));
  });

  it("loads synthetic inputs without submitting or deciding", async () => {
    const id = "80000000-0000-4000-8000-000000000008";
    const client: WorkflowClient = {
      submit: vi.fn().mockResolvedValue({
        id, correlation_id: id, status: "created", decision: "pending",
        payload: {}, execution_complete: false, failure_code: null,
      }), read: vi.fn(), decide: vi.fn(),
      listHistory: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
      activity: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    };
    render(<WorkflowWorkspace signedIn client={client} profile={orderResolutionProfile} signIn={vi.fn()} signOut={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("Synthetic use case"), "ORS-001");
    await userEvent.click(screen.getByRole("button", { name: "Load use case" }));
    expect((screen.getByLabelText("Order issue data (JSON)") as HTMLTextAreaElement).value).toContain("ORDER-LOW");
    const amount = screen.getByLabelText("order amount");
    await userEvent.clear(amount);
    await userEvent.type(amount, "91.00");
    await userEvent.click(screen.getByLabelText("policy evidence 1 current"));
    const data = JSON.parse((screen.getByLabelText("Order issue data (JSON)") as HTMLTextAreaElement).value);
    expect(data.order.amount).toBe("91.00");
    expect(data.policy_evidence[0].current).toBe(false);
    expect(screen.getByText(/Loading only prepares input/)).toBeVisible();
    expect(client.submit).not.toHaveBeenCalled();
    expect(client.decide).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Reviewer object ID"), id);
    await userEvent.clear(screen.getByLabelText("order delay days"));
    await userEvent.click(screen.getByRole("button", { name: "Submit issue" }));
    expect(client.submit).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("order delay days"), "7");
    await userEvent.click(screen.getByRole("button", { name: "Submit issue" }));
    await waitFor(() => expect(client.submit).toHaveBeenCalledWith(id, expect.objectContaining({
      order: expect.objectContaining({ amount: "91.00", delay_days: 7 }),
      policy_evidence: [expect.objectContaining({ current: false })],
    }), expect.any(String)));
    expect(client.decide).not.toHaveBeenCalled();
  });

  it("reports approval not required rather than a pending decision", async () => {
    const record: WorkflowCase = {
      id: "80000000-0000-4000-8000-000000000008",
      correlation_id: "80000000-0000-4000-8000-000000000008",
      status: "pending", decision: "pending",
      payload: { proposal: { version: 1, action: "manual_review", destination_id: "synthetic", approval_required: false } },
      decision_handle: "opaque", decision_channel: "api", execution_complete: false, failure_code: null,
    };
    const client: WorkflowClient = {
      submit: vi.fn(), read: vi.fn().mockResolvedValue(record), decide: vi.fn(),
      listHistory: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
      activity: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    };
    render(<WorkflowWorkspace signedIn client={client} profile={orderResolutionProfile} signIn={vi.fn()} signOut={vi.fn()} />);
    revealCaseLookup();
    fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: record.id } });
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByText("Approval not required.")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Approval" })).queryByText(/Decision: pending/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(client.decide).not.toHaveBeenCalled();
  });

  it("discloses an unavailable use-case catalog", () => {
    const client: WorkflowClient = {
      submit: vi.fn(), read: vi.fn(), decide: vi.fn(),
      listHistory: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
      activity: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    };
    const profile = {
      ...orderResolutionProfile,
      useCaseCatalog: { schema_version: "workflow-use-cases/1" as const, status: "unavailable" as const, scenario_set: null, cases: [] as const },
    };
    render(<WorkflowWorkspace signedIn client={client} profile={profile} signIn={vi.fn()} signOut={vi.fn()} />);
    expect(screen.getByText("Synthetic use cases are unavailable for the selected assets.")).toBeVisible();
    expect(screen.queryByLabelText("Synthetic use case")).not.toBeInTheDocument();
  });

  it("does not infer approval is required from pending status", async () => {
    const record: WorkflowCase = {
      id: "80000000-0000-4000-8000-000000000008",
      correlation_id: "80000000-0000-4000-8000-000000000008",
      status: "pending", decision: "pending",
      payload: { proposal: { version: 1, action: "manual_review", destination_id: "synthetic" } },
      decision_handle: "opaque", decision_channel: "api", execution_complete: false, failure_code: null,
    };
    const client: WorkflowClient = {
      submit: vi.fn(), read: vi.fn().mockResolvedValue(record), decide: vi.fn(),
      listHistory: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
      activity: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    };
    render(<WorkflowWorkspace signedIn client={client} profile={orderResolutionProfile} signIn={vi.fn()} signOut={vi.fn()} />);
    revealCaseLookup();
    fireEvent.change(screen.getByLabelText("Case ID"), { target: { value: record.id } });
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByText("Approval requirement is unavailable.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(client.decide).not.toHaveBeenCalled();
  });
});
