import { Component, useState, type ReactNode } from "react";
import type { RootOptions } from "react-dom/client";

import type { WorkflowCase } from "../api";
import type { StudioProtocolAdapter, StudioProtocolContext, WorkflowStudioProfile } from "../studio-profile";

const statuses = new Set(["created", "pending", "approved", "rejected", "completed", "failed"]);

export class ProtocolBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed
      ? <p role="alert">Protocol context could not be shared.</p>
      : this.props.children;
  }
}

export const reportStudioCaughtError: NonNullable<RootOptions["onCaughtError"]> = (_error, info) => {
  if (info.errorBoundary instanceof ProtocolBoundary) {
    console.error("Protocol context could not be shared.");
  } else {
    console.error("An application component could not be displayed.");
  }
};

function ProtocolControl({ name, adapter: Adapter, context }: {
  name: string;
  adapter: StudioProtocolAdapter;
  context: StudioProtocolContext;
}) {
  const [active, setActive] = useState(false);
  return (
    <div>
      <button className="secondary" type="button" onClick={() => setActive((value) => !value)}>
        {active ? `Stop sharing with ${name}` : `Share status with ${name}`}
      </button>
      {active && <ProtocolBoundary><Adapter context={context} /></ProtocolBoundary>}
    </div>
  );
}

export function ProtocolContextPanel({ record, profile }: {
  record: WorkflowCase;
  profile: WorkflowStudioProfile;
}) {
  const agUi = profile.capabilities.agUi && profile.protocolAdapters?.agUi;
  const copilotKit = profile.capabilities.copilotKit && profile.protocolAdapters?.copilotKit;
  if (!agUi && !copilotKit) return null;
  if (!statuses.has(record.status)) return <p role="alert">Protocol context is unavailable for this status.</p>;
  const context = Object.freeze({
    description: "Selected authorized case status",
    value: JSON.stringify({ status: record.status }),
  });
  return (
    <section aria-label="Protocol context">
      <p>Share only this case's status with an optional integration. It may send the status on a later agent run. Stopping or selecting another case requests removal.</p>
      {agUi && <ProtocolControl name="AG-UI" adapter={agUi} context={context} />}
      {copilotKit && <ProtocolControl name="CopilotKit" adapter={copilotKit} context={context} />}
    </section>
  );
}
