ALTER TABLE order_resolution_hosted_bindings
    ALTER COLUMN caller_id DROP NOT NULL,
    ALTER COLUMN session_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS order_resolution_hosted_decision_intents (
    case_id uuid PRIMARY KEY REFERENCES wf_cases(id) ON DELETE CASCADE,
    proposal_version integer NOT NULL CHECK (proposal_version > 0),
    action text NOT NULL,
    destination_id text NOT NULL,
    handle_digest char(64) NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor_id text NOT NULL,
    tenant_id text NOT NULL,
    decision_scope text NOT NULL,
    decision_channel text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
