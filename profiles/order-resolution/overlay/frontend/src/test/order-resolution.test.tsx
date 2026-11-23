import { describe, expect, it } from "vitest";

import type { WorkflowCase } from "../api";
import { orderResolutionProfile } from "../order-resolution";


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
      execution_complete: false,
      failure_code: null,
    };
    expect(orderResolutionProfile.decisionBinding?.(record)).toEqual({
      proposal_version: 3,
      action: "manual_review",
      destination_id: "synthetic-destination",
      handle: "opaque-handle",
      channel: "api",
    });
  });
});
