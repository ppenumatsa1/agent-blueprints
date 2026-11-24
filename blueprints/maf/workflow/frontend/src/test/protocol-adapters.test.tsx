import { useEffect } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowCase, WorkflowClient } from "../api";
import { defaultWorkflowStudioProfile } from "../default-profile";
import { reportStudioCaughtError } from "../components/protocol-context-panel";
import { createAgUiContextAdapter, createCopilotKitContextAdapter } from "../protocol-adapters";
import type { StudioProtocolContext, WorkflowStudioProfile } from "../studio-profile";
import { WorkflowWorkspace } from "../workspace";

const record: WorkflowCase = {
  id: "80000000-0000-4000-8000-000000000008",
  correlation_id: "90000000-0000-4000-8000-000000000009",
  status: "pending",
  decision: "pending",
  payload: { secret: "PRIVATE PAYLOAD" },
  decision_handle: "PRIVATE HANDLE",
  execution_complete: false,
  failure_code: "PRIVATE FAILURE",
};

function setup(profile: WorkflowStudioProfile) {
  const client: WorkflowClient = {
    submit: vi.fn(),
    read: vi.fn().mockResolvedValue(record),
    decide: vi.fn(),
    listHistory: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    activity: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  };
  const result = render(
    <WorkflowWorkspace profile={profile} signedIn client={client} signIn={vi.fn()} signOut={vi.fn()} />,
    { onCaughtError: reportStudioCaughtError },
  );
  return { client, ...result };
}

async function selectCase() {
  await userEvent.type(screen.getByLabelText("Case ID"), record.id);
  await userEvent.click(screen.getByRole("button", { name: /^Open$/ }));
  await screen.findByRole("heading", { name: "Case status: pending" });
}

describe("read-only protocol context", () => {
  it("does not activate absent or disabled integrations", async () => {
    const register = vi.fn(() => vi.fn());
    setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, copilotKit: true },
      protocolAdapters: { agUi: createAgUiContextAdapter(register) },
    });
    await selectCase();
    expect(register).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Protocol context" })).not.toBeInTheDocument();
    expect(screen.getByText("CopilotKit: Not enabled")).toBeVisible();
  });

  it("shares only a protocol context entry after consent and removes it on stop or deselection", async () => {
    const unregister = vi.fn();
    const register = vi.fn(() => unregister);
    const contexts: StudioProtocolContext[] = [];
    const removeCopilot = vi.fn();
    const useContext = (context: StudioProtocolContext) => {
      useEffect(() => {
        contexts.push(context);
        return removeCopilot;
      }, [context.description, context.value]);
    };
    const { client, container, unmount } = setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, agUi: true, copilotKit: true },
      protocolAdapters: {
        agUi: createAgUiContextAdapter(register),
        copilotKit: createCopilotKitContextAdapter(useContext),
      },
    });
    await selectCase();
    expect(register).not.toHaveBeenCalled();
    expect(contexts).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Share status with AG-UI" }));
    await userEvent.click(screen.getByRole("button", { name: "Share status with CopilotKit" }));
    const expected = { description: "Selected authorized case status", value: '{"status":"pending"}' };
    expect(register).toHaveBeenCalledWith(expected);
    expect(contexts).toEqual([expected]);
    expect(JSON.stringify(register.mock.calls)).not.toMatch(/PRIVATE|80000000|90000000/);
    expect(client.submit).not.toHaveBeenCalled();
    expect(client.decide).not.toHaveBeenCalled();
    expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Stop sharing with AG-UI" }));
    expect(unregister).toHaveBeenCalledOnce();
    unmount();
    expect(removeCopilot).toHaveBeenCalledOnce();
  });

  it("isolates registration errors and keeps approval available", async () => {
    const { client } = setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, agUi: true },
      protocolAdapters: { agUi: createAgUiContextAdapter(() => { throw new Error("PRIVATE ERROR"); }) },
    });
    vi.mocked(client.read).mockResolvedValueOnce({ ...record, failure_code: null });
    await selectCase();
    await userEvent.click(screen.getByRole("button", { name: "Share status with AG-UI" }));
    expect(await screen.findByText("AG-UI context could not be shared.")).toBeVisible();
    expect(screen.queryByText("PRIVATE ERROR")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(client.decide).toHaveBeenCalledWith(record.id, "approved"));
  });

  it("refuses an unrecognized status instead of sending it to the adapter", async () => {
    const register = vi.fn(() => vi.fn());
    const { client } = setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, agUi: true },
      protocolAdapters: { agUi: createAgUiContextAdapter(register) },
    });
    const invalid: WorkflowCase = JSON.parse(JSON.stringify({ ...record, status: "PRIVATE STATUS" }));
    vi.mocked(client.read).mockResolvedValueOnce(invalid);
    await userEvent.type(screen.getByLabelText("Case ID"), record.id);
    await userEvent.click(screen.getByRole("button", { name: /^Open$/ }));
    expect(await screen.findByText("Protocol context is unavailable for this status.")).toBeVisible();
    expect(register).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Share status with AG-UI" })).not.toBeInTheDocument();
  });

  it("revokes sharing when the selected case is reloaded", async () => {
    const unregister = vi.fn();
    const register = vi.fn(() => unregister);
    setup({
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, agUi: true },
      protocolAdapters: { agUi: createAgUiContextAdapter(register) },
    });
    await selectCase();
    await userEvent.click(screen.getByRole("button", { name: "Share status with AG-UI" }));
    await userEvent.click(screen.getByRole("button", { name: /^Open$/ }));
    expect(unregister).toHaveBeenCalledOnce();
    expect(await screen.findByRole("button", { name: "Share status with AG-UI" })).toBeVisible();
    expect(register).toHaveBeenCalledOnce();
  });

  it("isolates a throwing CopilotKit hook", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const { client } = setup({
        ...defaultWorkflowStudioProfile,
        capabilities: { ...defaultWorkflowStudioProfile.capabilities, copilotKit: true },
        protocolAdapters: { copilotKit: createCopilotKitContextAdapter(() => { throw new Error("PRIVATE ERROR"); }) },
      });
      vi.mocked(client.read).mockResolvedValueOnce({ ...record, failure_code: null });
      await selectCase();
      await userEvent.click(screen.getByRole("button", { name: "Share status with CopilotKit" }));
      expect(screen.getByText("Protocol context could not be shared.")).toBeVisible();
      expect(screen.getByRole("button", { name: "Approve" })).toBeVisible();
      expect(consoleError).toHaveBeenCalledWith("Protocol context could not be shared.");
      expect(JSON.stringify(consoleError.mock.calls)).not.toContain("PRIVATE ERROR");
    } finally {
      consoleError.mockRestore();
    }
  });

  it("does not log exception text or component stacks from other boundaries", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      reportStudioCaughtError(new Error("PRIVATE EXCEPTION"), { componentStack: "PRIVATE STACK" });
      expect(consoleError).toHaveBeenCalledWith("An application component could not be displayed.");
      expect(JSON.stringify(consoleError.mock.calls)).not.toMatch(/PRIVATE EXCEPTION|PRIVATE STACK/);
    } finally {
      consoleError.mockRestore();
    }
  });
});
