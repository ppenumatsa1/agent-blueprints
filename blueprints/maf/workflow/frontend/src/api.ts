export type Decision = "pending" | "approved" | "rejected";
export type Scope = "read" | "write" | "approve";
export type WorkflowStatus = "created" | "pending" | "approved" | "rejected" | "completed" | "failed";
export type ActivityType =
  | "created"
  | "review_requested"
  | "request_recorded"
  | "decision_recorded"
  | "action_applied"
  | "action_failed"
  | "workflow_finished"
  | "recovery_failed"
  | "workflow_failed";

export interface WorkflowCase {
  id: string;
  correlation_id: string;
  status: "created" | "pending" | "approved" | "rejected" | "completed" | "failed";
  decision: Decision;
  payload: Record<string, unknown>;
  decision_handle?: string | null;
  decision_channel?: "api" | "foundry-responses" | null;
  execution_complete: boolean;
  failure_code: string | null;
}

export interface WorkflowHistoryItem {
  id: string;
  status: WorkflowStatus;
  decision: Decision;
  created_at: string;
  updated_at: string;
}

export interface WorkflowHistoryPage {
  schema_version: "workflow-history/1";
  items: WorkflowHistoryItem[];
  next_cursor: string | null;
}

export interface WorkflowActivityItem {
  type: ActivityType;
  created_at: string;
}

export interface WorkflowActivityPage {
  schema_version: "workflow-activity/1";
  items: WorkflowActivityItem[];
  next_cursor: string | null;
}

export interface DecisionBinding {
  proposal_version: number;
  action: string;
  destination_id: string;
  handle: string;
  channel: string;
}

export interface WorkflowClient {
  submit(reviewer: string, payload: Record<string, unknown>, idempotencyKey: string): Promise<WorkflowCase>;
  read(id: string): Promise<WorkflowCase>;
  listHistory(options?: {
    status?: WorkflowStatus;
    limit?: number;
    cursor?: string;
  }): Promise<WorkflowHistoryPage>;
  activity(id: string, options?: { limit?: number; cursor?: string; signal?: AbortSignal }): Promise<WorkflowActivityPage>;
  activityStream?(id: string, signal: AbortSignal, refresh: () => void): Promise<void>;
  decide(
    id: string,
    decision: "approved" | "rejected",
    binding?: DecisionBinding,
  ): Promise<WorkflowCase>;
}

export class WorkflowClientError extends Error {
  constructor(message: string, readonly authorizationFailure = false) {
    super(message);
  }
}

class TokenWaitError extends Error {}

function waitForToken(token: Promise<string>, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    let timer: ReturnType<typeof setTimeout>;
    const cleanup = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", aborted);
    };
    const aborted = () => {
      cleanup();
      reject(new TokenWaitError("Token acquisition was cancelled."));
    };
    timer = setTimeout(() => {
      cleanup();
      reject(new TokenWaitError("Token acquisition timed out."));
    }, 15_000);
    token.then(
      (value) => { cleanup(); resolve(value); },
      (error: unknown) => { cleanup(); reject(error); },
    );
    if (signal.aborted) {
      aborted();
      return;
    }
    signal.addEventListener("abort", aborted, { once: true });
  });
}

function newTraceparent(): string | undefined {
  try {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    const hex = (part: Uint8Array) => Array.from(part, (value) => value.toString(16).padStart(2, "0")).join("");
    const trace = hex(bytes.subarray(0, 16));
    const parent = hex(bytes.subarray(16));
    if (/^0+$/.test(trace) || /^0+$/.test(parent)) return undefined;
    return `00-${trace}-${parent}-01`;
  } catch {
    return undefined;
  }
}

function isWorkflowCase(value: unknown): value is WorkflowCase {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === "string" &&
    typeof record.correlation_id === "string" &&
    ["created", "pending", "approved", "rejected", "completed", "failed"].includes(String(record.status)) &&
    ["pending", "approved", "rejected"].includes(String(record.decision)) &&
    typeof record.payload === "object" &&
    record.payload !== null &&
    !Array.isArray(record.payload) &&
    (record.decision_handle === undefined ||
      record.decision_handle === null ||
      typeof record.decision_handle === "string") &&
    (record.decision_channel === undefined ||
      record.decision_channel === null ||
      record.decision_channel === "api" ||
      record.decision_channel === "foundry-responses") &&
    typeof record.execution_complete === "boolean" &&
    (record.failure_code === null || typeof record.failure_code === "string")
  );
}

const workflowStatuses: WorkflowStatus[] = ["created", "pending", "approved", "rejected", "completed", "failed"];
const activityTypes: ActivityType[] = [
  "created",
  "review_requested",
  "request_recorded",
  "decision_recorded",
  "action_applied",
  "action_failed",
  "workflow_finished",
  "recovery_failed",
  "workflow_failed",
];
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const timestampPattern = /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  return Object.keys(value).length === expected.length && expected.every((key) => key in value);
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && timestampPattern.test(value) && Number.isFinite(Date.parse(value));
}

function isCursor(value: unknown): value is string | null {
  return value === null || (typeof value === "string" && value.length > 0 && value.length <= 512);
}

function isHistoryPage(value: unknown): value is WorkflowHistoryPage {
  if (!isRecord(value) || !hasExactKeys(value, ["schema_version", "items", "next_cursor"])) return false;
  return (
    value.schema_version === "workflow-history/1" &&
    isCursor(value.next_cursor) &&
    Array.isArray(value.items) &&
    value.items.every((item) =>
      isRecord(item) &&
      hasExactKeys(item, ["id", "status", "decision", "created_at", "updated_at"]) &&
      typeof item.id === "string" &&
      uuidPattern.test(item.id) &&
      workflowStatuses.includes(item.status as WorkflowStatus) &&
      ["pending", "approved", "rejected"].includes(String(item.decision)) &&
      isTimestamp(item.created_at) &&
      isTimestamp(item.updated_at),
    )
  );
}

function isActivityPage(value: unknown): value is WorkflowActivityPage {
  if (!isRecord(value) || !hasExactKeys(value, ["schema_version", "items", "next_cursor"])) return false;
  return (
    value.schema_version === "workflow-activity/1" &&
    isCursor(value.next_cursor) &&
    Array.isArray(value.items) &&
    value.items.every((item) =>
      isRecord(item) &&
      hasExactKeys(item, ["type", "created_at"]) &&
      activityTypes.includes(item.type as ActivityType) &&
      isTimestamp(item.created_at),
    )
  );
}

export class HttpWorkflowClient implements WorkflowClient {
  constructor(private readonly tokenFor: (scope: Scope) => Promise<string>) {}

  private async token(scope: Scope, signal?: AbortSignal): Promise<string> {
    try {
      const token = this.tokenFor(scope);
      return await (signal ? waitForToken(token, signal) : token);
    } catch (reason) {
      if (reason instanceof TokenWaitError) throw new WorkflowClientError(reason.message);
      throw new WorkflowClientError("Sign in again or grant the required permission.", true);
    }
  }

  private async request<T>(
    scope: Scope,
    path: string,
    validate: (value: unknown) => value is T,
    options: { body?: unknown; idempotencyKey?: string; signal?: AbortSignal } = {},
  ): Promise<T> {
    const token = await this.token(scope, options.signal);
    let response: Response;
    try {
      const traceparent = newTraceparent();
      response = await fetch(path, {
        method: options.body === undefined ? "GET" : "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
          ...(traceparent ? { traceparent } : {}),
        },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: "omit",
        signal: options.signal,
      });
    } catch {
      throw new WorkflowClientError("The service could not be reached. Check the record before retrying.");
    }
    if (!response.ok) {
      if (response.status === 401) throw new WorkflowClientError("Your session is invalid or expired.", true);
      if (response.status === 403) throw new WorkflowClientError("You are not authorized for this record.", true);
      if (response.status === 404) throw new WorkflowClientError("The record was not found.", true);
      if (response.status === 409) throw new WorkflowClientError("The request conflicts with the current record.");
      throw new WorkflowClientError("The request failed. Check the record before retrying.");
    }
    const data: unknown = await response.json();
    if (!validate(data)) throw new WorkflowClientError("The service returned an invalid response.");
    return data;
  }

  submit(reviewer: string, payload: Record<string, unknown>, idempotencyKey: string): Promise<WorkflowCase> {
    return this.request("write", "/api/cases", isWorkflowCase, {
      body: { reviewer_id: reviewer, payload },
      idempotencyKey,
    });
  }

  read(id: string): Promise<WorkflowCase> {
    return this.request("read", `/api/cases/${encodeURIComponent(id)}`, isWorkflowCase);
  }

  listHistory(options: { status?: WorkflowStatus; limit?: number; cursor?: string } = {}): Promise<WorkflowHistoryPage> {
    const query = new URLSearchParams();
    if (options.status) query.set("status", options.status);
    if (options.limit !== undefined) query.set("limit", String(options.limit));
    if (options.cursor) query.set("cursor", options.cursor);
    const suffix = query.size ? `?${query.toString()}` : "";
    return this.request("read", `/api/cases${suffix}`, isHistoryPage);
  }

  activity(id: string, options: { limit?: number; cursor?: string; signal?: AbortSignal } = {}): Promise<WorkflowActivityPage> {
    const query = new URLSearchParams();
    if (options.limit !== undefined) query.set("limit", String(options.limit));
    if (options.cursor) query.set("cursor", options.cursor);
    const suffix = query.size ? `?${query.toString()}` : "";
    return this.request(
      "read",
      `/api/cases/${encodeURIComponent(id)}/activity${suffix}`,
      isActivityPage,
      { signal: options.signal },
    );
  }

  async activityStream(id: string, signal: AbortSignal, refresh: () => void): Promise<void> {
    const token = await this.token("read", signal);
    if (signal.aborted) return;
    const connection = new AbortController();
    const abort = () => connection.abort();
    signal.addEventListener("abort", abort, { once: true });
    const connectTimeout = setTimeout(abort, 15_000);
    try {
      const response = await fetch(`/api/cases/${encodeURIComponent(id)}/activity/stream`, {
        headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
        credentials: "omit",
        signal: connection.signal,
      });
      clearTimeout(connectTimeout);
      if ([401, 403, 404].includes(response.status)) {
        throw new WorkflowClientError("Activity access is no longer available.", true);
      }
      if (!response.ok || !response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) {
        throw new WorkflowClientError("Live activity is unavailable.");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (!signal.aborted) {
          let idleTimeout: ReturnType<typeof setTimeout> | undefined;
          const idle = new Promise<never>((_resolve, reject) => {
            idleTimeout = setTimeout(() => {
              reject(new WorkflowClientError("Live activity timed out."));
              connection.abort();
            }, 20_000);
          });
          let part: ReadableStreamReadResult<Uint8Array>;
          try {
            part = await Promise.race([reader.read(), idle]);
          } finally {
            clearTimeout(idleTimeout);
          }
          if (part.done) break;
          buffer += decoder.decode(part.value, { stream: true }).replace(/\r/g, "");
          if (buffer.length > 8192) throw new WorkflowClientError("Live activity returned an invalid response.");
          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const event = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            if (event === "event: activity.refresh\ndata: {}") refresh();
            else if (event === "event: unavailable\ndata: {}") {
              throw new WorkflowClientError("Activity access is no longer available.", true);
            } else if (event === "event: retry\ndata: {}") {
              throw new WorkflowClientError("Live activity is temporarily unavailable.");
            } else if (event !== ": heartbeat") {
              throw new WorkflowClientError("Live activity returned an invalid response.");
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
      } finally {
        await reader.cancel();
      }
    } finally {
      clearTimeout(connectTimeout);
      signal.removeEventListener("abort", abort);
      connection.abort();
    }
  }

  decide(
    id: string,
    decision: "approved" | "rejected",
    binding?: DecisionBinding,
  ): Promise<WorkflowCase> {
    return this.request("approve", `/api/cases/${encodeURIComponent(id)}/decision`, isWorkflowCase, {
      body: { decision, ...binding },
    });
  }
}
