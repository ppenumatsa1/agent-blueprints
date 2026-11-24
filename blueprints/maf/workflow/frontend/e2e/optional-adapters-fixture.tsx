import { createRoot } from "react-dom/client";

import type { WorkflowCase, WorkflowClient } from "../src/api";
import { defaultWorkflowStudioProfile } from "../src/default-profile";
import { WorkflowWorkspace } from "../src/workspace";
import "../src/styles.css";

const record: WorkflowCase = {
  id: "80000000-0000-4000-8000-000000000008",
  correlation_id: "90000000-0000-4000-8000-000000000009",
  status: "pending",
  decision: "pending",
  payload: { evidence: "Approved synthetic evidence", secret: "Not projected" },
  execution_complete: false,
  failure_code: null,
};
const unavailable = async (): Promise<never> => { throw new Error("Not available in fixture"); };
const projectionFails = new URLSearchParams(location.search).has("projection-error");
const client: WorkflowClient = {
  submit: unavailable,
  read: async () => record,
  decide: async () => ({ ...record, status: "completed", decision: "approved", execution_complete: true }),
  listHistory: async () => ({ schema_version: "workflow-history/1", items: [], next_cursor: null }),
  activity: async () => ({ schema_version: "workflow-activity/1", items: [], next_cursor: null }),
};

const root = document.getElementById("root");
if (!root) throw new Error("Missing fixture root");
createRoot(root).render(
  <WorkflowWorkspace
    signedIn
    client={client}
    signIn={unavailable}
    signOut={unavailable}
    profile={{
      ...defaultWorkflowStudioProfile,
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, evidence: true, manualTests: true },
      projectPayload: () => ({ summary: "Synthetic request", fields: [] }),
      projectEvidence: (selected) => {
        if (projectionFails) throw new Error("Private projection failure");
        return {
          heading: "Review evidence",
          items: [{ label: "Approved", value: String(selected.payload.evidence) }],
        };
      },
      syntheticManualTests: [{
        label: "Run synthetic check",
        run: async () => {
          document.body.dataset.manualTestInvoked = "true";
          return { outcome: "failed", summary: "Synthetic assertion failed" };
        },
      }],
    }}
  />,
);
