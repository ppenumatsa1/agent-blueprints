import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
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
  const disclosure = document.querySelector<HTMLDetailsElement>(".case-lookup");
  if (disclosure && !disclosure.open) {
    const summary = disclosure.querySelector("summary");
    if (summary) fireEvent.click(summary);
  }
  await userEvent.type(screen.getByLabelText("Case ID"), record.id);
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  await screen.findByRole("status", { name: "Case status: pending" });
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

  it("never exposes or invokes manual tests even when explicitly enabled in development", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const run = vi.fn(async () => {
      await fetch("/api/real-business-action", { method: "POST" });
      return { outcome: "passed" as const, summary: "Unexpected success" };
    });
    const { client } = setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, manualTests: true },
      syntheticManualTests: [{ label: "Run synthetic", run }],
    });
    expect(screen.getByRole("region", { name: "Synthetic manual tests" })).toHaveTextContent("Unavailable");
    expect(screen.queryByRole("button", { name: "Run synthetic" })).not.toBeInTheDocument();
    await openCase();
    expect(screen.queryByText(/Manual tests:/)).not.toBeInTheDocument();
    expect(run).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("Unexpected success")).not.toBeInTheDocument();
    expect(client.submit).not.toHaveBeenCalled();
    expect(client.read).toHaveBeenCalledOnce();
    expect(client.decide).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("does not even inspect legacy test configuration when enabled", async () => {
    const getTests = vi.fn((): never => { throw new Error("test configuration accessed"); });
    setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, manualTests: true },
      get syntheticManualTests() { return getTests(); },
    });
    await openCase();
    expect(screen.queryByText(/Manual tests:/)).not.toBeInTheDocument();
    expect(getTests).not.toHaveBeenCalled();
  });
});
