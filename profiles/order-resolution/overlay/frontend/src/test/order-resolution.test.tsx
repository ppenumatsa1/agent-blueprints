import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowCase, WorkflowClient } from "../api";
import { orderResolutionProfile } from "../order-resolution";
import { WorkflowWorkspace } from "../workspace";


describe("order resolution case", () => {
  it("renders the deterministic proposal and escalated rejection", () => {
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
        { label: "Outcome", value: "Escalated after rejection" },
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
      payload: { proposal: { version: 3, action: "manual_review", destination_id: "synthetic" } },
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
});
