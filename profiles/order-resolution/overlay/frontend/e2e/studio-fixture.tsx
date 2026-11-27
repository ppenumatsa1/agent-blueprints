import { createRoot } from "react-dom/client";
import type { WorkflowClient } from "../src/api";
import { orderResolutionProfile } from "../src/order-resolution";
import { WorkflowWorkspace } from "../src/workspace";
import indexHtml from "../index.html?raw";
import "../src/styles.css";

const theme = new DOMParser().parseFromString(indexHtml, "text/html").querySelector("style");
if (!theme) throw new Error("Missing theme.");
document.head.appendChild(theme);

const client: WorkflowClient = {
  submit: async () => { throw new Error("Not implemented."); },
  read: async () => { throw new Error("Not implemented."); },
  decide: async () => { throw new Error("Not implemented."); },
  listHistory: async () => ({ schema_version: "workflow-history/1", items: [], next_cursor: null }),
  activity: async () => ({ schema_version: "workflow-activity/1", items: [], next_cursor: null }),
};

const root = document.getElementById("root");
if (!root) throw new Error("Missing fixture root.");
createRoot(root).render(
  <WorkflowWorkspace profile={orderResolutionProfile} signedIn client={client} signIn={async () => {}} signOut={async () => {}} />,
);
