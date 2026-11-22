import type { WorkflowCase } from "./api";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "Unavailable";
}

export function OrderResolutionCase({ record }: { record: WorkflowCase }) {
  const order = object(record.payload.order);
  const proposal = object(record.payload.proposal);
  if (!("id" in order) || !("action" in proposal)) {
    return <pre>{JSON.stringify(record.payload, null, 2)}</pre>;
  }
  const amount = typeof proposal.amount === "string"
    ? `${text(proposal.currency)} ${proposal.amount}`
    : "Not applicable";
  const outcome = record.status === "rejected" ? "Escalated after rejection" : record.status;

  return (
    <dl aria-label="Order resolution details">
      <dt>Order</dt>
      <dd>{text(order.id)}</dd>
      <dt>Issue</dt>
      <dd>{text(order.issue)}</dd>
      <dt>Proposed action</dt>
      <dd>{text(proposal.action)}</dd>
      <dt>Proposed amount</dt>
      <dd>{amount}</dd>
      <dt>Approval required</dt>
      <dd>{proposal.approval_required === true ? "Yes" : "No"}</dd>
      <dt>Outcome</dt>
      <dd>{outcome}</dd>
    </dl>
  );
}

export const orderResolutionUi = {
  title: "Order Resolution",
  description: "Resolve synthetic order issues with deterministic policy and authorized review.",
} as const;
