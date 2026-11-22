import { useRef, useState, type FormEvent, type ReactNode } from "react";

import { WorkflowClientError, type WorkflowCase, type WorkflowClient } from "./api";

export interface WorkspaceProps {
  signedIn: boolean;
  authBusy?: boolean;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
  client: WorkflowClient;
  renderCase?(record: WorkflowCase): ReactNode;
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function message(error: unknown): string {
  return error instanceof WorkflowClientError ? error.message : "The request could not be completed.";
}

export function WorkflowWorkspace({
  signedIn,
  authBusy = false,
  signIn,
  signOut,
  client,
  renderCase,
}: WorkspaceProps) {
  const [reviewer, setReviewer] = useState("");
  const [payload, setPayload] = useState("{}");
  const [recordId, setRecordId] = useState("");
  const [record, setRecord] = useState<WorkflowCase | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);

  async function run(operation: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await operation();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      if (!uuid.test(reviewer)) throw new WorkflowClientError("Enter a reviewer object ID.");
      let data: unknown;
      try {
        data = JSON.parse(payload);
      } catch {
        throw new WorkflowClientError("Request data must be valid JSON.");
      }
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        throw new WorkflowClientError("Request data must be a JSON object.");
      }
      const fingerprint = JSON.stringify({ reviewer, data });
      if (submission.current?.fingerprint !== fingerprint) {
        if (!globalThis.crypto?.randomUUID) throw new WorkflowClientError("Secure request IDs are unavailable.");
        submission.current = { fingerprint, key: globalThis.crypto.randomUUID() };
      }
      const result = await client.submit(reviewer, data as Record<string, unknown>, submission.current.key);
      setRecord(result);
      setRecordId(result.id);
    });
  }

  async function open(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      if (!uuid.test(recordId)) throw new WorkflowClientError("Enter a valid record ID.");
      setRecord(await client.read(recordId));
    });
  }

  async function decide(decision: "approved" | "rejected") {
    if (!record) return;
    const rawProposal = record.payload.proposal;
    const proposal = rawProposal && typeof rawProposal === "object" && !Array.isArray(rawProposal)
      ? rawProposal as Record<string, unknown>
      : undefined;
    const binding = proposal
      && typeof proposal.version === "number"
      && typeof proposal.action === "string"
      && typeof proposal.destination_id === "string"
      && typeof record.decision_handle === "string"
      ? {
          proposal_version: proposal.version,
          action: proposal.action,
          destination_id: proposal.destination_id,
          handle: record.decision_handle,
          channel: "api",
        }
      : undefined;
    await run(async () => setRecord(
      binding
        ? await client.decide(record.id, decision, binding)
        : await client.decide(record.id, decision),
    ));
  }

  const status = record?.status === "completed" && !record.execution_complete ? "recovering" : record?.status;
  return (
    <main className="shell">
      <header className="header">
        <div>
          <p className="eyebrow">Reusable MAF blueprint</p>
          <h1>Workflow workspace</h1>
          <p>Submit a request and review its durable approval state.</p>
        </div>
        {signedIn && (
          <button className="secondary" disabled={busy || authBusy} onClick={() => void run(signOut)}>
            Sign out
          </button>
        )}
      </header>
      {error && <p className="alert" role="alert">{error}</p>}
      {authBusy && <p role="status">Completing sign-in...</p>}
      {!signedIn ? (
        <section className="card">
          <h2>Sign in to continue</h2>
          <p>Use an authorized Microsoft Entra account for this application.</p>
          <button disabled={busy || authBusy} onClick={() => void run(signIn)}>Sign in</button>
        </section>
      ) : (
        <div className="layout">
          <section className="card">
            <h2>New request</h2>
            <p>The assigned reviewer must authorize the action.</p>
            <form onSubmit={create}>
              <label htmlFor="reviewer">Reviewer object ID</label>
              <input
                id="reviewer"
                value={reviewer}
                onChange={(event) => setReviewer(event.target.value)}
                autoComplete="off"
                required
              />
              <label htmlFor="payload">Request data (JSON)</label>
              <textarea id="payload" value={payload} onChange={(event) => setPayload(event.target.value)} rows={6} />
              <button type="submit" disabled={busy}>Submit request</button>
            </form>
          </section>
          <section className="card">
            <h2>Open a record</h2>
            <form onSubmit={open}>
              <label htmlFor="record-id">Record ID</label>
              <div className="inline">
                <input id="record-id" value={recordId} onChange={(event) => setRecordId(event.target.value)} />
                <button className="secondary" type="submit" disabled={busy}>Open</button>
              </div>
            </form>
            {busy && <p role="status">Working...</p>}
            {record && (
              <div className="record" aria-live="polite">
                <h3>Record status: {status}</h3>
                <p>Decision: <strong>{record.decision}</strong></p>
                <p className="identifier">Record ID: {record.id}</p>
                {record.failure_code && <p className="alert">Recovery or action failed. Check the record before retrying.</p>}
                {renderCase ? renderCase(record) : <pre>{JSON.stringify(record.payload, null, 2)}</pre>}
                {record.status === "pending" && record.decision === "pending" && (
                  <div className="actions">
                    <button disabled={busy} onClick={() => void decide("approved")}>Approve</button>
                    <button className="secondary" disabled={busy} onClick={() => void decide("rejected")}>Reject</button>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
