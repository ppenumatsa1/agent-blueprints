import { useState, type FormEvent } from "react";

import type { WorkflowStudioProfile } from "../studio-profile";
import { UseCaseEditor } from "./use-case-editor";

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
  const [selectedId, setSelectedId] = useState("");
  const [loadedId, setLoadedId] = useState("");
  const [editorValue, setEditorValue] = useState<Record<string, unknown>>({});
  const catalog = profile.useCaseCatalog;
  const cases = catalog?.status === "available" ? catalog.cases : [];
  const selected = cases.find((item) => item.id === selectedId);
  const loaded = cases.find((item) => item.id === loadedId);

  function loadUseCase() {
    if (!selected) return;
    onPayloadChange(JSON.stringify(selected.payload, null, 2));
    setEditorValue({ ...selected.payload });
    setLoadedId(selected.id);
  }

  const payloadControl = (
    <>
      <label htmlFor="payload">{profile.labels.payload}</label>
      <textarea
        id="payload"
        value={payload}
        onChange={(event) => {
          setLoadedId("");
          onPayloadChange(event.target.value);
        }}
        rows={6}
        disabled={busy}
      />
    </>
  );

  return (
    <section className="card request-composer" aria-labelledby="request-heading">
      <h2 id="request-heading">{profile.labels.newRequest}</h2>
      <p>{profile.labels.requestGuidance}</p>
      <form onSubmit={onSubmit}>
        {catalog?.status === "available" && (
          <div className="use-case-picker">
            <label htmlFor="use-case">Synthetic use case</label>
            <select
              id="use-case"
              value={selectedId}
              disabled={busy}
              onChange={(event) => setSelectedId(event.target.value)}
            >
              <option value="">Choose a use case</option>
              {cases.map((item) => <option value={item.id} key={item.id}>{item.id}: {item.title}</option>)}
            </select>
            <button type="button" className="secondary" disabled={busy || !selected} onClick={loadUseCase}>
              Load use case
            </button>
            <p className="hint">Loading only prepares input; it does not run a test or submit a case.</p>
            {loaded && (
              <div className="use-case-preview">
                <p role="status"><strong>Loaded: {loaded.id}</strong> — {loaded.title}</p>
                <p className="hint">Synthetic policy inputs are not independently verified evidence.</p>
                <UseCaseEditor template={loaded.payload} value={editorValue} disabled={busy}
                  onChange={(value) => {
                    setEditorValue(value);
                    onPayloadChange(JSON.stringify(value, null, 2));
                  }} />
              </div>
            )}
          </div>
        )}
        {catalog?.status === "unavailable" && (
          <p className="alert" role="status">Synthetic use cases are unavailable for the selected assets.</p>
        )}
        <label htmlFor="reviewer">{profile.labels.reviewer}</label>
        <input
          id="reviewer"
          value={reviewer}
          onChange={(event) => onReviewerChange(event.target.value)}
          autoComplete="off"
          required
          disabled={busy}
        />
        {payloadControl}
        <button type="submit" disabled={busy}>{profile.labels.submit}</button>
      </form>
    </section>
  );
}

