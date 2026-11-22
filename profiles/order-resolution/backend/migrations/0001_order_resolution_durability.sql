-- Application-owned records only. Native MAF checkpoints remain owned by MAF.
CREATE TABLE IF NOT EXISTS order_resolution_requests (
    tenant_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    request_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    case_id UUID NOT NULL REFERENCES wf_cases(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, owner_id, request_key),
    UNIQUE (case_id)
);

CREATE TABLE IF NOT EXISTS order_resolution_proposals (
    case_id UUID NOT NULL REFERENCES wf_cases(id),
    proposal_version INTEGER NOT NULL CHECK (proposal_version > 0),
    tenant_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    input_digest TEXT NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
    policy_evidence_digest TEXT NOT NULL CHECK (policy_evidence_digest ~ '^[0-9a-f]{64}$'),
    policy_version TEXT NOT NULL,
    action TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    approval_required BOOLEAN NOT NULL,
    reason_codes JSONB NOT NULL,
    decision_handle_digest TEXT CHECK (decision_handle_digest ~ '^[0-9a-f]{64}$'),
    decision_expires_at TIMESTAMPTZ,
    decision_channel TEXT,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, proposal_version),
    UNIQUE (case_id, proposal_version, action, destination_id),
    CHECK (
        (decision_handle_digest IS NULL AND decision_expires_at IS NULL
            AND decision_channel IS NULL)
        OR
        (approval_required AND decision_handle_digest IS NOT NULL
            AND decision_expires_at IS NOT NULL AND decision_channel IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS order_resolution_one_current_proposal
    ON order_resolution_proposals (case_id)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS order_resolution_decisions (
    case_id UUID NOT NULL,
    proposal_version INTEGER NOT NULL,
    action TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    decision_scope TEXT NOT NULL,
    decision_channel TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (case_id, proposal_version),
    FOREIGN KEY (case_id, proposal_version, action, destination_id)
        REFERENCES order_resolution_proposals
            (case_id, proposal_version, action, destination_id)
);

CREATE TABLE IF NOT EXISTS order_resolution_effects (
    case_id UUID NOT NULL,
    proposal_version INTEGER NOT NULL,
    action TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    effect_key TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    request_body BYTEA NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('claimed', 'unknown', 'verified')),
    result_digest TEXT CHECK (result_digest ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, proposal_version, action, destination_id),
    FOREIGN KEY (case_id, proposal_version, action, destination_id)
        REFERENCES order_resolution_proposals
            (case_id, proposal_version, action, destination_id),
    CHECK (
        (status = 'verified' AND result_digest IS NOT NULL)
        OR (status <> 'verified' AND result_digest IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS order_resolution_synthetic_effects (
    effect_key TEXT PRIMARY KEY,
    request_digest TEXT NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    request_body BYTEA NOT NULL,
    result_digest TEXT NOT NULL CHECK (result_digest ~ '^[0-9a-f]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_resolution_actions (
    case_id UUID NOT NULL,
    proposal_version INTEGER NOT NULL,
    order_id TEXT NOT NULL,
    action TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    effect_key TEXT NOT NULL UNIQUE,
    amount NUMERIC(18, 2),
    currency TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, proposal_version, action, destination_id),
    FOREIGN KEY (case_id, proposal_version, action, destination_id)
        REFERENCES order_resolution_proposals
            (case_id, proposal_version, action, destination_id)
);

CREATE TABLE IF NOT EXISTS order_resolution_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES wf_cases(id),
    event TEXT NOT NULL,
    actor_id TEXT,
    reason_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
