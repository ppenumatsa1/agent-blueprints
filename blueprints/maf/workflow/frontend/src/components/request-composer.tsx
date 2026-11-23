import type { FormEvent } from "react";

import type { WorkflowStudioProfile } from "../studio-profile";

interface RequestComposerProps {
  profile: WorkflowStudioProfile;
  reviewer: string;
  payload: string;
  busy: boolean;
  onReviewerChange(value: string): void;
  onPayloadChange(value: string): void;
  onSubmit(event: FormEvent): void;
}

export function RequestComposer({
  profile,
  reviewer,
  payload,
  busy,
  onReviewerChange,
  onPayloadChange,
  onSubmit,
}: RequestComposerProps) {
  return (
    <section className="card">
      <h2>{profile.labels.newRequest}</h2>
      <p>{profile.labels.requestGuidance}</p>
      <form onSubmit={onSubmit}>
        <label htmlFor="reviewer">{profile.labels.reviewer}</label>
        <input
          id="reviewer"
          value={reviewer}
          onChange={(event) => onReviewerChange(event.target.value)}
          autoComplete="off"
          required
        />
        <label htmlFor="payload">{profile.labels.payload}</label>
        <textarea
          id="payload"
          value={payload}
          onChange={(event) => onPayloadChange(event.target.value)}
          rows={6}
        />
        <button type="submit" disabled={busy}>{profile.labels.submit}</button>
      </form>
    </section>
  );
}

