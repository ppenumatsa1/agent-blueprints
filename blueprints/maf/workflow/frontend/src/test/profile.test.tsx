import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowCase, WorkflowClient } from "../api";
import { defaultWorkflowStudioProfile } from "../default-profile";
import type { WorkflowStudioProfile } from "../studio-profile";
import { WorkflowWorkspace } from "../workspace";

const record: WorkflowCase = {
  id: "80000000-0000-4000-8000-000000000008",
  correlation_id: "90000000-0000-4000-8000-000000000009",
  status: "pending",
  decision: "pending",
  payload: { summary: "Synthetic profile request", category: "sample" },
  execution_complete: false,
  failure_code: null,
};

const client: WorkflowClient = {
  submit: vi.fn().mockResolvedValue(record),
  read: vi.fn().mockResolvedValue(record),
  decide: vi.fn().mockResolvedValue(record),
};

describe("workflow studio profiles", () => {
  it("uses generic default labels and a plain-text payload projection", () => {
    const projection = defaultWorkflowStudioProfile.projectPayload(record.payload, record);
    expect(defaultWorkflowStudioProfile.title).toBe("Workflow workspace");
    expect(defaultWorkflowStudioProfile.description).not.toMatch(/order|refund|shipment|customer/i);
    expect(projection).toEqual({
      summary: "Synthetic profile request",
      fields: [
        { label: "category", value: "sample" },
      ],
    });
  });

  it("renders profile-owned labels and payload rendering", async () => {
    const profile: WorkflowStudioProfile = {
      ...defaultWorkflowStudioProfile,
      title: "Synthetic Review Studio",
      labels: { ...defaultWorkflowStudioProfile.labels, openCase: "Find synthetic case" },
      renderPayload: (projection) => <p>Projected: {projection.summary}</p>,
    };
    render(
      <WorkflowWorkspace
        profile={profile}
        signedIn
        client={client}
        signIn={vi.fn()}
        signOut={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: "Synthetic Review Studio" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Find synthetic case" })).toBeVisible();
  });
});
