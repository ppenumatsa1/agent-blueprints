import type { PayloadProjection, WorkflowStudioProfile } from "./studio-profile";

function display(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === null) return "None";
  return "Structured value";
}

function projectPayload(payload: Record<string, unknown>): PayloadProjection {
  const entries = Object.entries(payload)
    .filter(([label]) => label !== "summary")
    .slice(0, 6);
  return {
    summary: typeof payload.summary === "string"
      ? payload.summary
      : entries.length === 0
        ? "No request details were supplied."
        : `${entries.length} request field${entries.length === 1 ? "" : "s"} available.`,
    fields: entries.map(([label, value]) => ({ label, value: display(value) })),
  };
}

export const defaultWorkflowStudioProfile: WorkflowStudioProfile = {
  title: "Workflow workspace",
  description: "Submit a request and review its durable approval state.",
  eyebrow: "Reusable workflow application",
  labels: {
    newRequest: "New request",
    requestGuidance: "The assigned reviewer must authorize the action.",
    reviewer: "Reviewer object ID",
    payload: "Request data (JSON)",
    submit: "Submit request",
    openCase: "Open a case",
    caseId: "Case ID",
    open: "Open",
    approve: "Approve",
    reject: "Reject",
  },
  capabilities: {
    history: false,
    liveActivity: false,
    evidence: false,
    manualTests: false,
    agUi: false,
    copilotKit: false,
  },
  projectPayload,
};

