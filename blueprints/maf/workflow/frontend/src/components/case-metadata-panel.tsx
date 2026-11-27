import type { WorkflowCase } from "../api";

export function CaseMetadataPanel({
  record,
  status,
}: {
  record: WorkflowCase;
  status: string;
}) {
  return (
    <div className="metadata-panel">
      <h2>Run Metadata</h2>
      <dl className="metadata" aria-label="Case metadata">
        <div><dt>Status</dt><dd>{status}</dd></div>
        <div><dt>Decision</dt><dd>{record.decision}</dd></div>
        <div><dt>Case ID</dt><dd className="identifier">{record.id}</dd></div>
        <div><dt>Correlation ID</dt><dd className="identifier">{record.correlation_id}</dd></div>
      </dl>
    </div>
  );
}

