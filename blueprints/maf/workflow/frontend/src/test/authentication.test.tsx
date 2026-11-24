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

it("clears record data and ignores stale active accounts when the signed-in user changes", async () => {
  const first = {
    homeAccountId: "same-home", tenantId: "first", localAccountId: "first", username: "first@example.test",
  };
  const second = {
    homeAccountId: "same-home", tenantId: "second", localAccountId: "second", username: "second@example.test",
  };
  const instance = {
    getActiveAccount: vi.fn().mockReturnValue(first),
    acquireTokenSilent: vi.fn().mockResolvedValue({ accessToken: "synthetic-token" }),
  };
  const id = "80000000-0000-4000-8000-000000000008";
  let streamSignal: AbortSignal | undefined;
  vi.stubGlobal("fetch", vi.fn((path: string, options: RequestInit) => {
    if (path.endsWith("/activity/stream")) {
      streamSignal = options.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        options.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      });
    }
    const body = path.includes("/activity")
      ? { schema_version: "workflow-activity/1", items: [], next_cursor: null }
      : path === "/api/cases"
        ? { schema_version: "workflow-history/1", items: [], next_cursor: null }
        : {
          id, correlation_id: id, status: "pending", decision: "pending",
          payload: { summary: "Private synthetic record" }, execution_complete: false, failure_code: null,
        };
    return Promise.resolve({ ok: true, json: async () => body });
  }));
  const config = {
    tenantId: "10000000-0000-4000-8000-000000000001",
    clientId: "20000000-0000-4000-8000-000000000002",
    scopes: { read: "read", write: "write", approve: "approve" },
  };
  useMsal.mockReturnValue({ instance, accounts: [first], inProgress: InteractionStatus.None });
  const { rerender } = render(<AuthenticatedApplication config={config} />);
  await userEvent.type(screen.getByLabelText("Case ID"), id);
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(await screen.findByRole("heading", { name: "Case status: pending" })).toBeVisible();
  await waitFor(() => expect(streamSignal).toBeDefined());

  useMsal.mockReturnValue({ instance, accounts: [second], inProgress: InteractionStatus.None });
  rerender(<AuthenticatedApplication config={config} />);
  expect(streamSignal?.aborted).toBe(true);
  expect(screen.queryByRole("heading", { name: "Case status: pending" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Case ID")).toHaveValue("");
  await userEvent.type(screen.getByLabelText("Case ID"), id);
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(instance.acquireTokenSilent).toHaveBeenLastCalledWith({ account: second, scopes: ["read"] });
});
