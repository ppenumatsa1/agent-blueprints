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
  history: {
    heading: "Workflow history",
    activityHeading: "Event Timeline",
    loadMore: "Load more history",
    loading: "Loading history...",
    empty: "No workflows found.",
    activityEmpty: "No activity records are available for this workflow.",
    error: "Workflow history could not be loaded.",
    events: {
      created: "Workflow created",
      review_requested: "Review requested",
      request_recorded: "Workflow request recorded",
      decision_recorded: "Decision recorded",
      action_applied: "Action applied",
      action_failed: "Action failed",
      workflow_finished: "Workflow finished",
      recovery_failed: "Recovery failed",
      workflow_failed: "Workflow failed",
    },
  },
  capabilities: {
    history: true,
    liveActivity: true,
    evidence: false,
    manualTests: false,
    agUi: false,
    copilotKit: false,
  },
  projectPayload,
};

