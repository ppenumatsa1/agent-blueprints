import { useState } from "react";
import { createRoot } from "react-dom/client";

import type { WorkflowClient } from "../src/api";
import { ActivityTimeline } from "../src/components/activity-timeline";
import { HistorySidebar } from "../src/components/history-sidebar";
import { defaultWorkflowStudioProfile } from "../src/default-profile";
import "./../src/styles.css";

const recordId = "80000000-0000-4000-8000-000000000008";

const client: WorkflowClient = {
  submit: async () => { throw new Error("Not implemented in the browser fixture."); },
  read: async () => { throw new Error("Not implemented in the browser fixture."); },
  decide: async () => { throw new Error("Not implemented in the browser fixture."); },
  listHistory: async () => ({
    schema_version: "workflow-history/1",
    items: [{
      id: recordId,
      status: "pending",
      decision: "pending",
      created_at: "2026-01-01T00:00:00+00:00",
      updated_at: "2026-01-01T00:00:00+00:00",
    }],
    next_cursor: null,
  }),
  activity: async () => ({
    schema_version: "workflow-activity/1",
    items: [{ type: "created", created_at: "2026-01-01T00:00:00+00:00" }],
    next_cursor: null,
  }),
};

function HistoryBrowserFixture() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return (
    <main className="shell">
      <h1>History browser fixture</h1>
      <HistorySidebar
        profile={defaultWorkflowStudioProfile}
        client={client}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />
      {selectedId && (
        <ActivityTimeline
          caseId={selectedId}
          client={client}
          profile={defaultWorkflowStudioProfile}
        />
      )}
    </main>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("The browser fixture root is missing.");
createRoot(root).render(<HistoryBrowserFixture />);
