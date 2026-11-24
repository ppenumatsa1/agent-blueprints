import { createRoot } from "react-dom/client";

import type { WorkflowCase, WorkflowClient } from "../src/api";
import { defaultWorkflowStudioProfile } from "../src/default-profile";
import { createAgUiContextAdapter } from "../src/protocol-adapters";
import { WorkflowWorkspace } from "../src/workspace";
import "../src/styles.css";

const record: WorkflowCase = {
  id: "80000000-0000-4000-8000-000000000008",
  correlation_id: "90000000-0000-4000-8000-000000000009",
  status: "pending",
  decision: "pending",
  payload: { private: "PRIVATE PAYLOAD" },
  execution_complete: false,
  failure_code: null,
};
const unavailable = async (): Promise<never> => { throw new Error("Not available in fixture"); };
const client: WorkflowClient = {
  submit: unavailable,
  read: async () => record,
  decide: unavailable,
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
      projectPayload: () => ({ summary: "Synthetic request", fields: [] }),
      capabilities: { ...defaultWorkflowStudioProfile.capabilities, agUi: true },
      protocolAdapters: {
        agUi: createAgUiContextAdapter((context) => {
          const output = document.createElement("output");
          output.setAttribute("aria-label", "Synthetic protocol consumer");
          output.textContent = JSON.stringify(context);
          document.body.appendChild(output);
          return () => output.remove();
        }),
      },
    }}
  />,
);
