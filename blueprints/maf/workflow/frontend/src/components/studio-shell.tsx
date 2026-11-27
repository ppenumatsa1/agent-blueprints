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
      if (recordRequest.current === requestNumber) setRecord(result);
    });
  }

  async function selectHistoryRecord(id: string) {
    const requestNumber = ++recordRequest.current;
    setRecordId(id);
    setRecord(null);
    await run(async () => {
      const result = await client.read(id);
      if (recordRequest.current === requestNumber) setRecord(result);
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

  const status = record?.status === "completed" && !record.execution_complete ? "recovering" : record?.status;
  return (
    <main className="shell">
      <header className="header">
        <div>
          <p className="eyebrow">{profile.eyebrow}</p>
          <h1>{profile.title}</h1>
          <p>{profile.description}</p>
        </div>
        {signedIn && (
          <button className="secondary" disabled={busy || authBusy} onClick={() => void run(signOut)}>
            Sign out
          </button>
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
          <section className="card">
            <h2>{profile.labels.openCase}</h2>
            <form onSubmit={open}>
              <label htmlFor="record-id">{profile.labels.caseId}</label>
              <div className="inline">
                <input id="record-id" value={recordId} onChange={(event) => setRecordId(event.target.value)} />
                <button className="secondary" type="submit" disabled={busy}>{profile.labels.open}</button>
              </div>
            </form>
            {busy && <p role="status">Working...</p>}
            {record && status && (
              <div className="record" aria-live="polite">
                <h3>Case status: {status}</h3>
                {record.failure_code && (
                  <p className="alert">Recovery or action failed. Check the case before retrying.</p>
                )}
                <CaseMetadataPanel record={record} status={status} profile={profile} />
                <CaseSummaryPanel record={record} profile={profile} />
                <ProtocolContextPanel key={record.id} record={record} profile={profile} />
                {profile.capabilities.history && (
                  <ActivityTimeline
                    caseId={record.id}
                    client={client}
                    profile={profile}
                    refreshKey={activityRefresh}
                  />
                )}
              </div>
            )}
          </section>
          </div>
          <aside className="card review-rail" aria-label="Review and evidence">
            {record ? (
              <>
                <ApprovalPanel
                  decision={record.decision}
                  pending={record.status === "pending" && record.decision === "pending" && !record.failure_code && (!profile.decisionBinding || !!profile.decisionBinding(record)) && (!profile.approvalRequired || profile.approvalRequired(record) === true)}
                  busy={busy}
                  profile={profile}
                  onDecide={(value) => void decide(value)}
                />
                {profile.approvalRequired && profile.approvalRequired(record) === undefined && (
                  <p>Approval requirement is unavailable.</p>
                )}
                {profile.capabilities.evidence && profile.projectEvidence ? (
                  <EvidencePanel record={record} project={profile.projectEvidence} />
                ) : <section><h3>Evidence</h3><p>Evidence is not available in this view.</p></section>}
              </>
            ) : <><h2>Review and evidence</h2><p>Open a case to review its status.</p></>}
          </aside>
        </div>
      )}
    </main>
  );
}

