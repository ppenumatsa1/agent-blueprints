import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WorkflowCase } from "../api";
import { OrderResolutionCase } from "../order-resolution";


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
    render(<OrderResolutionCase record={record} />);
    expect(screen.getByText("ORDER-HIGH")).toBeVisible();
    expect(screen.getByText("partial_refund_10")).toBeVisible();
    expect(screen.getByText("USD 18.50")).toBeVisible();
    expect(screen.getByText("Escalated after rejection")).toBeVisible();
  });
});
