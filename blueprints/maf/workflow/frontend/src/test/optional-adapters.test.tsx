import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowCase, WorkflowClient } from "../api";
import { defaultWorkflowStudioProfile } from "../default-profile";
import { OptionalBoundary } from "../components/optional-boundary";
import type { WorkflowStudioProfile } from "../studio-profile";
import { WorkflowWorkspace } from "../workspace";

const record: WorkflowCase = {
  id: "80000000-0000-4000-8000-000000000008",
  correlation_id: "90000000-0000-4000-8000-000000000009",
  status: "pending",
  decision: "pending",
  payload: { summary: "Synthetic request", approvedEvidence: "Safe example", privateValue: "DO NOT DISPLAY" },
  execution_complete: false,
  failure_code: null,
};

function setup(profile: WorkflowStudioProfile) {
  const client: WorkflowClient = {
    submit: vi.fn(),
    read: vi.fn().mockResolvedValue(record),
    decide: vi.fn(),
    listHistory: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    activity: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  };
  const rendered = render(<WorkflowWorkspace profile={profile} signedIn client={client} signIn={vi.fn()} signOut={vi.fn()} />);
  return { client, ...rendered };
}

async function openCase() {
  await userEvent.type(screen.getByLabelText("Case ID"), record.id);
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  await screen.findByRole("heading", { name: "Case status: pending" });
}

describe("optional studio adapters", () => {
  it("does not execute disabled or missing adapters", async () => {
    const projectEvidence = vi.fn();
    const run = vi.fn();
    const { client } = setup({ ...defaultWorkflowStudioProfile, projectEvidence, syntheticManualTests: [{ label: "Run synthetic", run }] });
    await openCase();
    expect(projectEvidence).not.toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Run synthetic" })).not.toBeInTheDocument();
    expect(client.read).toHaveBeenCalledOnce();
  });

  it("renders only the application allowlist, without fetching evidence or creating links", async () => {
    const { client, container } = setup({
      ...defaultWorkflowStudioProfile,
      projectPayload: () => ({ summary: "Safe summary", fields: [] }),
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, evidence: true },
      projectEvidence: (selected) => ({
        heading: "Review evidence",
        items: [{ label: "Approved field", value: String(selected.payload.approvedEvidence) }],
      }),
    });
    expect(screen.queryByRole("region", { name: "Review evidence" })).not.toBeInTheDocument();
    await openCase();
    expect(screen.getByRole("region", { name: "Review evidence" })).toHaveTextContent("Safe example");
    expect(screen.queryByText("DO NOT DISPLAY")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Review evidence" }).querySelector("a")).toBeNull();
    expect(client.read).toHaveBeenCalledOnce();
    expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  });

  it("isolates projection failures and keeps approval usable", async () => {
    const { client } = setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, evidence: true },
      projectEvidence: () => { throw new Error("sensitive exception"); },
    });
    await openCase();
    expect(screen.getByRole("alert")).toHaveTextContent("Evidence could not be displayed");
    expect(screen.queryByText("sensitive exception")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(client.decide).toHaveBeenCalledWith(record.id, "approved");
  });

  it("runs synthetic tests only on request and reports failures without synthetic success", async () => {
    const run = vi.fn().mockRejectedValueOnce(new Error("private diagnostic")).mockResolvedValueOnce({ outcome: "failed", summary: "Assertion failed" });
    const { client } = setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, manualTests: true },
      syntheticManualTests: [{ label: "Run synthetic", run }],
    });
    const button = await screen.findByRole("button", { name: "Run synthetic" });
    expect(run).not.toHaveBeenCalled();
    await userEvent.click(button);
    expect(await screen.findByText("Manual test could not be completed.")).toBeVisible();
    expect(screen.queryByText("private diagnostic")).not.toBeInTheDocument();
    await userEvent.click(button);
    expect(await screen.findByText("Failed: Assertion failed")).toBeVisible();
    expect(client.submit).not.toHaveBeenCalled();
    expect(client.read).not.toHaveBeenCalled();
    expect(client.decide).not.toHaveBeenCalled();
  });

  it("isolates an optional component load failure", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    function Broken(): never { throw new Error("load failed"); }
    try {
      render(<><OptionalBoundary><Broken /></OptionalBoundary><p>Workflow remains available</p></>);
      expect(screen.getByRole("alert")).toHaveTextContent("Synthetic tests could not be loaded");
      expect(screen.getByText("Workflow remains available")).toBeVisible();
    } finally {
      consoleError.mockRestore();
    }
  });
});
