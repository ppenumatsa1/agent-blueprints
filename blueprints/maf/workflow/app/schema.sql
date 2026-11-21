CREATE TABLE IF NOT EXISTS wf_cases (
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('created', 'pending', 'approved', 'rejected', 'completed', 'failed')),
    request_id TEXT,
    checkpoint_id TEXT,
    terminal_checkpoint_id TEXT,
    execution_complete BOOLEAN NOT NULL DEFAULT FALSE,
    failure_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, owner_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS wf_decisions (
    case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wf_action_ledger (
    case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
    action_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wf_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES wf_cases(id),
    event TEXT NOT NULL,
    actor_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
