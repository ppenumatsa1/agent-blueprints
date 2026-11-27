import { useEffect, useRef, useState, type FormEvent } from "react";

import { WorkflowClientError, type WorkflowCase, type WorkflowClient } from "../api";
import type { WorkflowStudioProfile } from "../studio-profile";
import { ApprovalPanel } from "./approval-panel";
import { CaseMetadataPanel } from "./case-metadata-panel";
import { CaseSummaryPanel } from "./case-summary-panel";
import { ActivityTimeline } from "./activity-timeline";
import { HistorySidebar } from "./history-sidebar";
import { RequestComposer } from "./request-composer";
import { EvidencePanel } from "./evidence-panel";
import { ProtocolContextPanel } from "./protocol-context-panel";

export interface StudioShellProps {
  profile: WorkflowStudioProfile;
  signedIn: boolean;
  authBusy?: boolean;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
  client: WorkflowClient;
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function message(error: unknown): string {
  return error instanceof WorkflowClientError ? error.message : "The request could not be completed.";
}

export function StudioShell({
  profile,
  signedIn,
  authBusy = false,
  signIn,
  signOut,
  client,
}: StudioShellProps) {
  const [reviewer, setReviewer] = useState("");
  const [payload, setPayload] = useState("{}");
  const [recordId, setRecordId] = useState("");
  const [record, setRecord] = useState<WorkflowCase | null>(null);
  const [newRun, setNewRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refreshError, setRefreshError] = useState("");
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [activityRefresh, setActivityRefresh] = useState(0);
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);
  const recordRequest = useRef(0);

  useEffect(() => {
    if (!signedIn || busy || !record || record.execution_complete) return;
    const current = record;
    const requestNumber = recordRequest.current;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let timeout: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    function schedule() {
      timer = setTimeout(() => {
        const request = new AbortController();
        controller = request;
        const expired = new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => {
            request.abort();
            reject(new WorkflowClientError("Case refresh timed out."));
          }, 15_000);
        });
        const read = Promise.resolve().then(() => client.read(current.id, { signal: request.signal }));
        void Promise.race([read, expired]).then((updated) => {
          if (active && recordRequest.current === requestNumber) {
            setRefreshError("");
            setRecord(updated);
            if (updated.status !== current.status || updated.decision !== current.decision || updated.execution_complete !== current.execution_complete) {
              setHistoryRefresh((value) => value + 1);
              setActivityRefresh((value) => value + 1);
            }
            schedule();
          }
        }).catch((reason: unknown) => {
          if (active && recordRequest.current === requestNumber) {
            if (reason instanceof WorkflowClientError && reason.authorizationFailure) {
              setRecord(null);
            } else {
              schedule();
            }
            setRefreshError(message(reason));
          }
        }).finally(() => {
          clearTimeout(timeout);
        });
      }, 5_000);
    }
    schedule();
    return () => {
      active = false;
      clearTimeout(timer);
      clearTimeout(timeout);
      controller?.abort();
    };
  }, [signedIn, busy, record, client]);

  async function run(operation: () => Promise<void>) {
    setError("");
    setRefreshError("");
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
      recordRequest.current += 1;
      setRecord(result);
      setRecordId(result.id);
      setNewRun(false);
      setHistoryRefresh((value) => value + 1);
    });
  }

  async function open(event: FormEvent) {
    event.preventDefault();
    const requestNumber = ++recordRequest.current;
    await run(async () => {
      if (!uuid.test(recordId)) throw new WorkflowClientError("Enter a valid case ID.");
      setRecord(null);
      const result = await client.read(recordId);
      if (recordRequest.current === requestNumber) {
        setRecord(result);
        setNewRun(false);
      }
    });
  }

  async function selectHistoryRecord(id: string) {
    const requestNumber = ++recordRequest.current;
    setRecordId(id);
    setRecord(null);
    await run(async () => {
      const result = await client.read(id);
      if (recordRequest.current === requestNumber) {
        setRecord(result);
        setNewRun(false);
      }
    });
  }

  async function decide(decision: "approved" | "rejected") {
    if (!record) return;
    recordRequest.current += 1;
    const binding = profile.decisionBinding?.(record);
    await run(async () => {
      const updated = binding
        ? await client.decide(record.id, decision, binding)
        : await client.decide(record.id, decision);
      setRecord(updated);
      setHistoryRefresh((value) => value + 1);
      setActivityRefresh((value) => value + 1);
    });
  }

  function startNewRun() {
    recordRequest.current += 1;
    setRecord(null);
    setRecordId("");
    setReviewer("");
    setPayload("{}");
    submission.current = null;
    setNewRun(true);
    setError("");
    setRefreshError("");
  }

  async function refreshWorkspace() {
    await run(async () => {
      setHistoryRefresh((value) => value + 1);
      setActivityRefresh((value) => value + 1);
      if (record) {
        const updated = await client.read(record.id);
        setRecord(updated);
      }
    });
  }

  const status = record?.status === "completed" && !record.execution_complete ? "recovering" : record?.status;
  return (
    <main className="shell">
      <header className="header">
        <div>
          <p className="eyebrow">{profile.eyebrow}</p>
          <h1>{profile.title}</h1>
          <p className="header-description">{profile.description}</p>
        </div>
        {signedIn && (
          <div className="header-actions" role="group" aria-label="Workflow actions">
            <button type="button" onClick={startNewRun} disabled={busy || newRun}>New Run</button>
            <button type="button" className="secondary" disabled={busy || authBusy}
              onClick={() => void refreshWorkspace()}>Refresh</button>
            <button className="secondary" disabled={busy || authBusy} onClick={() => void run(signOut)}>
              Sign out
            </button>
          </div>
        )}
      </header>
      {(error || refreshError) && <p className="alert" role="alert">{error || refreshError}</p>}
      {authBusy && <p role="status">Completing sign-in...</p>}
      {!signedIn ? (
        <section className="card">
          <h2>Sign in to continue</h2>
          <p>Use an authorized Microsoft Entra account for this application.</p>
          <button disabled={busy || authBusy} onClick={() => void run(signIn)}>Sign in</button>
        </section>
      ) : (
        <div className={`layout${profile.capabilities.history ? "" : " without-history"}`}>
          {profile.capabilities.history && (
            <HistorySidebar
              profile={profile}
              client={client}
              selectedId={record?.id ?? null}
              refreshKey={historyRefresh}
              disabled={busy}
              onSelect={(id) => void selectHistoryRecord(id)}
            />
          )}
          <div className="workflow-main">
            {newRun ? (
              <>
                <RequestComposer
                  profile={profile}
                  reviewer={reviewer}
                  payload={payload}
                  busy={busy}
                  onReviewerChange={setReviewer}
                  onPayloadChange={setPayload}
                  onSubmit={(event) => void create(event)}
                />
                {profile.capabilities.manualTests ? (
                  <section className="card" aria-label="Synthetic manual tests">
                    <h2>Synthetic manual tests</h2>
                    <p>Unavailable: application-supplied test code is not isolated from real systems.</p>
                  </section>
                ) : null}
                <details className="card case-lookup">
                  <summary>{profile.labels.openCase}</summary>
                  <form onSubmit={open}>
                    <label htmlFor="record-id">{profile.labels.caseId}</label>
                    <div className="inline">
                      <input id="record-id" value={recordId}
                        onChange={(event) => setRecordId(event.target.value)} />
                      <button className="secondary" type="submit" disabled={busy}>{profile.labels.open}</button>
                    </div>
                  </form>
                </details>
              </>
            ) : record && status ? (
              <section className="card run-workspace" aria-labelledby="run-heading">
                <div className="run-heading">
                  <div>
                    <h2 id="run-heading">Selected run</h2>
                    <p className="identifier">{record.id}</p>
                  </div>
                  <span className={`status-badge status-${status}`} role="status" aria-label={`Case status: ${status}`}>
                    {status}
                  </span>
                </div>
                {record.failure_code && (
                  <p className="alert">Recovery or action failed. Check the case before retrying.</p>
                )}
                {profile.capabilities.history && (
                  <ActivityTimeline
                    caseId={record.id}
                    client={client}
                    profile={profile}
                    refreshKey={activityRefresh}
                  />
                )}
                <ProtocolContextPanel key={record.id} record={record} profile={profile} />
                <details className="case-lookup">
                  <summary>Open another case by ID</summary>
                  <form onSubmit={open}>
                    <label htmlFor="record-id">{profile.labels.caseId}</label>
                    <div className="inline">
                      <input id="record-id" value={recordId}
                        onChange={(event) => setRecordId(event.target.value)} />
                      <button className="secondary" type="submit" disabled={busy}>{profile.labels.open}</button>
                    </div>
                  </form>
                </details>
              </section>
            ) : (
              <section className="card" aria-live="polite">
                <h2>Loading workflow</h2>
                {busy && <p role="status">Working…</p>}
              </section>
            )}
          </div>
          <aside className="review-rail" aria-label="Workflow review">
            {record && status ? (
              <>
                <section className="card output-panel" aria-labelledby="output-heading">
                  <div className="panel-heading">
                    <h2 id="output-heading">Latest Output</h2>
                  </div>
                  <p>{record.failure_code
                    ? "The workflow reported a failure. Review the case before retrying."
                    : status === "pending" && record.decision === "pending"
                      ? "This workflow is awaiting its configured review decision."
                      : `Workflow state: ${status}.`}</p>
                  <p className="hint">A response transcript is not included in the case API.</p>
                </section>
                <section className="card">
                  <CaseSummaryPanel record={record} profile={profile} />
                </section>
                <section className="card">
                  <ApprovalPanel
                    decision={record.decision}
                    approvalRequired={profile.approvalRequired?.(record)}
                    pending={record.status === "pending" && record.decision === "pending" && !record.failure_code && (!profile.decisionBinding || !!profile.decisionBinding(record)) && (!profile.approvalRequired || profile.approvalRequired(record) === true)}
                    busy={busy}
                    profile={profile}
                    onDecide={(value) => void decide(value)}
                  />
                </section>
                {profile.capabilities.evidence && profile.projectEvidence ? (
                  <section className="card"><EvidencePanel record={record} project={profile.projectEvidence} /></section>
                ) : (
                  <section className="card evidence-unavailable">
                    <h2>Evidence</h2>
                    <p>Evidence is not available for this workflow.</p>
                  </section>
                )}
                <section className="card">
                  <CaseMetadataPanel record={record} status={status} />
                </section>
              </>
            ) : (
              <section className="card approval-empty">
                <h2>Human-in-the-loop</h2>
                <p>Select a workflow to view its approval state.</p>
              </section>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}

