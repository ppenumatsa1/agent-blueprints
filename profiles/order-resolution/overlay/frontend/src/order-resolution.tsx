import type { DecisionBinding, WorkflowCase } from "./api";
import catalog from "./order-resolution-use-cases.json";
import type { PayloadProjection, StudioUseCaseCatalog, WorkflowStudioProfile } from "./studio-profile";
import { defaultWorkflowStudioProfile } from "./default-profile";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "Unavailable";
}

function projectOrderResolution(record: WorkflowCase): PayloadProjection {
  const order = object(record.payload.order);
  const proposal = object(record.payload.proposal);
  if (!("id" in order) || !("action" in proposal)) {
    return { summary: "Order resolution details are unavailable.", fields: [] };
  }
  const amount = typeof proposal.amount === "string"
    ? `${text(proposal.currency)} ${proposal.amount}`
    : "Not applicable";
  return {
    summary: `Review ${text(proposal.action)} for ${text(order.id)}.`,
    fields: [
      { label: "Order", value: text(order.id) },
      { label: "Issue", value: text(order.issue) },
      { label: "Proposed action", value: text(proposal.action) },
      { label: "Proposed amount", value: amount },
      { label: "Approval required", value: proposal.approval_required === true ? "Yes" : proposal.approval_required === false ? "No" : "Unavailable" },
      { label: "Status", value: record.status },
    ],
  };
}

function decisionBinding(record: WorkflowCase): DecisionBinding | undefined {
  const proposal = object(record.payload.proposal);
  return typeof proposal.version === "number"
    && typeof proposal.action === "string"
    && typeof proposal.destination_id === "string"
    && typeof record.decision_handle === "string"
    && (record.decision_channel === "api" || record.decision_channel === "foundry-responses")
    ? {
        proposal_version: proposal.version,
        action: proposal.action,
        destination_id: proposal.destination_id,
        handle: record.decision_handle,
        channel: record.decision_channel,
      }
    : undefined;
}

export const orderResolutionProfile: WorkflowStudioProfile = {
  title: "Order Resolution",
  description: "Resolve synthetic order issues with deterministic policy and authorized review.",
  eyebrow: "Order resolution workflow",
  labels: {
    newRequest: "New order issue",
    requestGuidance: "Review the input before submitting. Some resolutions require an authorized reviewer.",
    reviewer: "Reviewer object ID",
    payload: "Order issue data (JSON)",
    submit: "Submit issue",
    openCase: "Open a resolution case",
    caseId: "Case ID",
    open: "Open",
    approve: "Approve",
    reject: "Reject",
  },
  history: defaultWorkflowStudioProfile.history,
  capabilities: {
    history: true,
    liveActivity: true,
    evidence: false,
    manualTests: false,
    agUi: false,
    copilotKit: false,
  },
  projectPayload: (_payload, record) => projectOrderResolution(record),
  decisionBinding,
  approvalRequired: (record) => {
    const required = object(record.payload.proposal).approval_required;
    return typeof required === "boolean" ? required : undefined;
  },
  useCaseCatalog: catalog as StudioUseCaseCatalog,
};
