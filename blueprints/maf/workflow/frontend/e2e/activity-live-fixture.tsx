import { createRoot } from "react-dom/client";

import { HttpWorkflowClient } from "../src/api";
import { ActivityTimeline } from "../src/components/activity-timeline";
import { defaultWorkflowStudioProfile } from "../src/default-profile";
import "../src/styles.css";

const client = new HttpWorkflowClient(async () => "synthetic-token");
const root = document.getElementById("root");
if (!root) throw new Error("The browser fixture root is missing.");
createRoot(root).render(
  <main className="shell">
    <ActivityTimeline
      caseId="80000000-0000-4000-8000-000000000008"
      client={client}
      profile={defaultWorkflowStudioProfile}
    />
  </main>,
);
