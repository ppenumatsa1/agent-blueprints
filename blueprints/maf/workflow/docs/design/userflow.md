# User flows

## Submit, review, and complete

The current UI supports one request at a time and requires an existing
authorized Entra configuration. CI uses synthetic identities and does not
perform interactive sign-in.
Before users can reach the API, an operator applies reviewed business
migrations; runtime startup rejects an outdated or drifted schema.

```mermaid
flowchart TD
    A[User opens local UI] --> B{Entra account signed in?}
    B -- No --> C[MSAL sign-in]
    C --> D{Token acquired?}
    D -- No --> E[Show safe auth error; no API call]
    D -- Yes --> F[Enter reviewer ID and JSON request]
    B -- Yes --> F
    F --> G[Client validates JSON and creates idempotency key]
    G --> H[API validates token, write scope, request and reviewer]
    H --> I{Authorized?}
    I -- No --> J[401/403; no workflow action]
    I -- Yes --> K[Persist request, then start native workflow]
    K --> L[Save private pending checkpoint]
    L --> M[Reviewer opens case]
    M --> N{Assigned reviewer with approve scope and role?}
    N -- No --> O[403; state unchanged]
    N -- Yes --> P[Persist decision before resuming]
    P --> Q{Approved?}
    Q -- Yes --> R[Apply transactional database action once]
    Q -- No --> S[Record rejection; do not apply action]
    R --> T[Persist terminal checkpoint and outcome]
    S --> T
```

## Request and approval sequence

```mermaid
sequenceDiagram
    actor Owner
    actor Reviewer
    participant Browser as React/MSAL
    participant API as FastAPI
    participant Policy as Server policy
    participant DB as PostgreSQL
    participant Host as Local MAF host

    Owner->>Browser: Sign in and submit JSON + reviewer
    Browser->>API: POST /api/cases + bearer + idempotency key
    API->>Policy: Validate scope and different reviewer
    Policy-->>API: Allow or deny
    API->>DB: Create case/audit (unique owner key)
    API->>Host: Start workflow
    Host->>DB: Acquire per-case advisory lock
    Host->>Host: Save and verify pending checkpoint
    API-->>Browser: Pending case
    Reviewer->>Browser: Read case and decide
    Browser->>API: POST /api/cases/{id}/decision
    API->>Policy: Validate tenant, reviewer, scope, role
    API->>DB: Record immutable decision
    API->>Host: Resume matching request under lock
    Host->>DB: Apply action + ledger in one transaction
    API-->>Browser: Terminal status or safe error
```

## Failure and retry behavior

- **Token acquisition or API authentication failure:** show a safe message;
  do not call the protected operation without a token.
- **Unauthorized record read/decision:** the API returns 403; browser-side
  hiding is not authorization. The owner and assigned reviewer restrictions
  are enforced by `CaseAccessPolicy`.
- **Network error during submission:** the client retains the idempotency key
  for the same request fingerprint. Reopening/retrying a different payload
  must not reuse it. Check the record before repeating an ambiguous action.
- **Decision conflict:** the API returns 409. A different decision or actor
  cannot replace an already persisted decision.
- **Action/checkpoint/recovery failure:** the API returns an explicit failure
  class; logs omit tokens and payloads. Do not delete checkpoints or blindly
  repeat an external side effect.
- **Telemetry export failure:** fixed sanitized failure signals are logged;
  the workflow result is unaffected. Missing Azure configuration instead
  stops startup. Neither signal proves cloud delivery.
- **Process crash:** startup recovery reconciles SQL state with local MAF
  checkpoints. The tested worker-kill windows cover decision persistence and
  database-action commit, not host failover or external systems.

## Implementation references

The browser journey is implemented by
[`authenticated-app.tsx`](../../frontend/src/authenticated-app.tsx),
[`api.ts`](../../frontend/src/api.ts), and
[`workspace.tsx`](../../frontend/src/workspace.tsx). API policy and transitions
are in `backend/app/api.py`, `backend/app/domain/policy.py`,
`backend/app/usecases/service.py`, and `backend/app/infrastructure/store.py`.
Tests under `backend/tests/test_security.py` and `backend/tests/test_core.py`
cover automated authorization and recovery. Live Entra login and role
assignment remain unverified.
