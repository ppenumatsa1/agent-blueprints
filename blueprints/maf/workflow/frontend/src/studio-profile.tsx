import type { ComponentType, ReactNode } from "react";

import type { ActivityType, DecisionBinding, WorkflowCase } from "./api";

export type StudioCapability = "history" | "liveActivity" | "evidence" | "manualTests" | "agUi" | "copilotKit";

export interface PayloadField {
  label: string;
  value: string;
}

export interface PayloadProjection {
  summary: string;
  fields: PayloadField[];
}

export interface EvidenceProjection {
  heading: string;
  items: ReadonlyArray<{ label: string; value: string }>;
}

/**
 * Legacy configuration only. The studio never executes these callbacks: browser
 * application code can access real services and is not a security sandbox.
 * This does not isolate other trusted profile code or ordinary workflow actions.
 */
export interface SyntheticManualTest {
  label: string;
  run(): Promise<{ outcome: "passed" | "failed"; summary: string }>;
}

export interface StudioProtocolContext {
  readonly description: string;
  readonly value: string;
}

export type StudioProtocolAdapter = ComponentType<{ context: StudioProtocolContext }>;

export interface WorkflowStudioProfile {
  title: string;
  description: string;
  eyebrow: string;
  labels: {
    newRequest: string;
    requestGuidance: string;
    reviewer: string;
    payload: string;
    submit: string;
    openCase: string;
    caseId: string;
    open: string;
    approve: string;
    reject: string;
  };
  history: {
    heading: string;
    activityHeading: string;
    refresh: string;
    loadMore: string;
    loading: string;
    empty: string;
    error: string;
    events: Record<ActivityType, string>;
  };
  capabilities: Record<StudioCapability, boolean>;
  projectPayload(payload: Record<string, unknown>, record: WorkflowCase): PayloadProjection;
  renderPayload?(projection: PayloadProjection, record: WorkflowCase): ReactNode;
  decisionBinding?(record: WorkflowCase): DecisionBinding | undefined;
  projectEvidence?(record: WorkflowCase): EvidenceProjection;
  /** @deprecated Manual test execution is disabled in all environments. */
  syntheticManualTests?: readonly SyntheticManualTest[];
  protocolAdapters?: {
    agUi?: StudioProtocolAdapter;
    copilotKit?: StudioProtocolAdapter;
  };
}

