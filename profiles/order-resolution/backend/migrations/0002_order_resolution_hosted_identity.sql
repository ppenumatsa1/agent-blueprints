CREATE TABLE IF NOT EXISTS order_resolution_hosted_operations (
    operation_id TEXT PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES wf_cases(id),
    operation_kind TEXT NOT NULL CHECK (
        operation_kind IN ('conversation', 'start', 'resume')
    ),
    request_digest TEXT NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'acknowledged', 'rejected', 'unknown')
    ),
    remote_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (status = 'acknowledged' AND remote_id IS NOT NULL)
        OR (status <> 'acknowledged' AND remote_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS order_resolution_hosted_bindings (
    case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
    caller_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    scopes JSONB NOT NULL,
    roles JSONB NOT NULL,
    principal_kind TEXT NOT NULL CHECK (principal_kind IN ('owner', 'reviewer')),
    channel TEXT NOT NULL CHECK (channel = 'foundry-responses'),
    hosted_status TEXT NOT NULL DEFAULT 'bound' CHECK (
        hosted_status IN ('bound', 'pending', 'decision-recorded', 'completed')
    ),
    pending_request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (hosted_status IN ('pending', 'decision-recorded', 'completed')
            AND pending_request_id IS NOT NULL)
        OR (hosted_status IN ('bound', 'completed') AND pending_request_id IS NULL)
    ),
    UNIQUE (caller_id, session_id, conversation_id)
);
