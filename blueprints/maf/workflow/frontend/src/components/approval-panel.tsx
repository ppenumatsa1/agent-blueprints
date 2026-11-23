import type { Decision } from "../api";
import type { WorkflowStudioProfile } from "../studio-profile";

export function ApprovalPanel({
  decision,
  pending,
  busy,
  profile,
  onDecide,
}: {
  decision: Decision;
  pending: boolean;
  busy: boolean;
  profile: WorkflowStudioProfile;
  onDecide(decision: "approved" | "rejected"): void;
}) {
  return (
    <section aria-labelledby="approval-heading">
      <h3 id="approval-heading">Approval</h3>
      {pending ? (
        <div className="actions">
          <button disabled={busy} onClick={() => onDecide("approved")}>{profile.labels.approve}</button>
          <button className="secondary" disabled={busy} onClick={() => onDecide("rejected")}>
            {profile.labels.reject}
          </button>
        </div>
      ) : <p>Decision: <strong>{decision}</strong></p>}
    </section>
  );
}

