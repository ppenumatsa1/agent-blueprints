export type Decision = "pending" | "approved" | "rejected";
export type Scope = "read" | "write" | "approve";

export interface WorkflowCase {
  id: string;
  correlation_id: string;
  status: "created" | "pending" | "approved" | "rejected" | "completed" | "failed";
  decision: Decision;
  payload: Record<string, unknown>;
  execution_complete: boolean;
  failure_code: string | null;
}

export interface WorkflowClient {
  submit(reviewer: string, payload: Record<string, unknown>, idempotencyKey: string): Promise<WorkflowCase>;
  read(id: string): Promise<WorkflowCase>;
  decide(id: string, decision: "approved" | "rejected"): Promise<WorkflowCase>;
}

export class WorkflowClientError extends Error {}

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
    typeof record.execution_complete === "boolean" &&
    (record.failure_code === null || typeof record.failure_code === "string")
  );
}

export class HttpWorkflowClient implements WorkflowClient {
  constructor(private readonly tokenFor: (scope: Scope) => Promise<string>) {}

  private async request(
    scope: Scope,
    path: string,
    options: { body?: unknown; idempotencyKey?: string } = {},
  ): Promise<WorkflowCase> {
    let token: string;
    try {
      token = await this.tokenFor(scope);
    } catch {
      throw new WorkflowClientError("Sign in again or grant the required permission.");
    }
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
      });
    } catch {
      throw new WorkflowClientError("The service could not be reached. Check the record before retrying.");
    }
    if (!response.ok) {
      if (response.status === 401) throw new WorkflowClientError("Your session is invalid or expired.");
      if (response.status === 403) throw new WorkflowClientError("You are not authorized for this record.");
      if (response.status === 404) throw new WorkflowClientError("The record was not found.");
      if (response.status === 409) throw new WorkflowClientError("The request conflicts with the current record.");
      throw new WorkflowClientError("The request failed. Check the record before retrying.");
    }
    const data: unknown = await response.json();
    if (!isWorkflowCase(data)) throw new WorkflowClientError("The service returned an invalid response.");
    return data;
  }

  submit(reviewer: string, payload: Record<string, unknown>, idempotencyKey: string): Promise<WorkflowCase> {
    return this.request("write", "/api/cases", {
      body: { reviewer_id: reviewer, payload },
      idempotencyKey,
    });
  }

  read(id: string): Promise<WorkflowCase> {
    return this.request("read", `/api/cases/${encodeURIComponent(id)}`);
  }

  decide(id: string, decision: "approved" | "rejected"): Promise<WorkflowCase> {
    return this.request("approve", `/api/cases/${encodeURIComponent(id)}/decision`, { body: { decision } });
  }
}
