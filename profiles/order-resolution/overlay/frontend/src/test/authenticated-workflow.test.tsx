import { InteractionStatus } from "@azure/msal-browser";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { AuthenticatedApplication } from "../authenticated-app";

const useMsal = vi.hoisted(() => vi.fn());
vi.mock("@azure/msal-react", () => ({ useMsal }));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

it("runs a synthetic authenticated UI flow with server-gated decisions", async () => {
  const id = "80000000-0000-4000-8000-000000000008";
  const reviewer = "90000000-0000-4000-8000-000000000009";
  const account = { homeAccountId: "home", tenantId: "tenant", localAccountId: "user", username: "synthetic@example.test" };
  const instance = {
    getActiveAccount: vi.fn().mockReturnValue(account),
    acquireTokenSilent: vi.fn().mockImplementation(async ({ scopes }: { scopes: string[] }) => ({
      accessToken: `token-${scopes[0]}`,
    })),
  };
  useMsal.mockReturnValue({ instance, accounts: [account], inProgress: InteractionStatus.None });
  const config = {
    tenantId: "10000000-0000-4000-8000-000000000001",
    clientId: "20000000-0000-4000-8000-000000000002",
    scopes: { read: "read", write: "write", approve: "approve" },
  };
  const proposal = { version: 3, action: "manual_review", destination_id: "synthetic", approval_required: true };
  const record = {
    id, correlation_id: id, status: "pending", decision: "pending",
    payload: { proposal }, decision_handle: null, decision_channel: "api",
    execution_complete: false, failure_code: null,
  };
  const bound = { ...record, decision_handle: "synthetic-handle" };
  const decisionRequests: Array<Record<string, unknown>> = [];
  let submitted = false;
  const fetcher = vi.fn(async (path: string, options: RequestInit) => {
    const headers = options.headers as Record<string, string>;
    const method = options.method ?? "GET";
    if (path === "/api/cases" && method === "POST") {
      expect(headers.Authorization).toBe("Bearer token-write");
      expect(headers["Idempotency-Key"]).toBeTruthy();
      expect(JSON.parse(String(options.body))).toMatchObject({
        reviewer_id: reviewer, payload: { order: { id: "ORDER-LOW", amount: "91.00" } },
      });
      submitted = true;
      return Response.json(record);
    }
    if (path.startsWith("/api/cases?")) {
      expect(headers.Authorization).toBe("Bearer token-read");
      return Response.json({
        schema_version: "workflow-history/1",
        items: submitted ? [{
          id, status: "pending", decision: "pending",
          created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
        }] : [],
        next_cursor: null,
      });
    }
    if (path === `/api/cases/${id}`) {
      expect(headers.Authorization).toBe("Bearer token-read");
      return Response.json(bound);
    }
    if (path.startsWith(`/api/cases/${id}/activity?`)) {
      expect(headers.Authorization).toBe("Bearer token-read");
      return Response.json({
        schema_version: "workflow-activity/1",
        items: [{ type: "review_requested", created_at: "2026-01-01T00:00:00Z" }],
        next_cursor: null,
      });
    }
    if (path.endsWith("/activity/stream")) {
      expect(headers.Authorization).toBe("Bearer token-read");
      return new Response(null, { status: 503 });
    }
    if (path === `/api/cases/${id}/decision` && method === "POST") {
      expect(headers.Authorization).toBe("Bearer token-approve");
      const body = JSON.parse(String(options.body)) as Record<string, unknown>;
      decisionRequests.push(body);
      if (body.decision === "approved") return new Response(null, { status: 403 });
      return Response.json({ ...bound, status: "rejected", decision: "rejected", execution_complete: true });
    }
    throw new Error(`Unexpected mocked endpoint: ${method} ${path}`);
  });
  vi.stubGlobal("fetch", fetcher);

  render(<AuthenticatedApplication config={config} />);
  await screen.findByText("No workflows found.");
  await userEvent.selectOptions(screen.getByLabelText("Synthetic use case"), "ORS-001");
  await userEvent.click(screen.getByRole("button", { name: "Load use case" }));
  await userEvent.clear(screen.getByLabelText("order amount"));
  await userEvent.type(screen.getByLabelText("order amount"), "91.00");
  expect(fetcher.mock.calls.filter(([path, options]) => path === "/api/cases" && options.method === "POST")).toHaveLength(0);
  expect(decisionRequests).toHaveLength(0);

  await userEvent.type(screen.getByLabelText("Reviewer object ID"), reviewer);
  await userEvent.click(screen.getByRole("button", { name: "Submit issue" }));
  await screen.findByRole("status", { name: "Case status: pending" });
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  await screen.findByText("Review requested");
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(id) }));
  await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("You are not authorized for this record.");
  expect(screen.getByRole("status", { name: "Case status: pending" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Reject" }));
  expect(await screen.findByRole("status", { name: "Case status: rejected" })).toBeVisible();
  expect(decisionRequests).toEqual(["approved", "rejected"].map((decision) => ({
    decision, proposal_version: 3, action: "manual_review", destination_id: "synthetic",
    handle: "synthetic-handle", channel: "api",
  })));
  await waitFor(() => expect(instance.acquireTokenSilent).toHaveBeenCalledWith({ account, scopes: ["approve"] }));
});
