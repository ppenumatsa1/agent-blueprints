import type { WorkflowCase } from "../api";
import type { StudioCapability, WorkflowStudioProfile } from "../studio-profile";

const capabilityLabels: Record<StudioCapability, string> = {
  history: "History",
  liveActivity: "Live activity",
  evidence: "Evidence",
  manualTests: "Manual tests",
  agUi: "AG-UI",
  copilotKit: "CopilotKit",
};

export function CaseMetadataPanel({
  record,
  status,
  profile,
}: {
  record: WorkflowCase;
  status: string;
  profile: WorkflowStudioProfile;
}) {
  return (
    <>
      <dl className="metadata" aria-label="Case metadata">
        <div><dt>Status</dt><dd>{status}</dd></div>
        <div><dt>Decision</dt><dd>{record.decision}</dd></div>
        <div><dt>Case ID</dt><dd className="identifier">{record.id}</dd></div>
        <div><dt>Correlation ID</dt><dd className="identifier">{record.correlation_id}</dd></div>
      </dl>
      <div className="capabilities" aria-label="Optional studio capabilities">
        {Object.entries(profile.capabilities).map(([capability, enabled]) => (
          <span className="capability" key={capability}>
            {capabilityLabels[capability as StudioCapability]}: {enabled &&
              (capability !== "evidence" || !!profile.projectEvidence) &&
              (capability !== "manualTests" || (import.meta.env.DEV && !!profile.syntheticManualTests?.length))
              ? "Enabled" : "Not enabled"}
          </span>
        ))}
      </div>
    </>
  );
}

