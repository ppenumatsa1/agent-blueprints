# User flow

```mermaid
sequenceDiagram
    actor Submitter
    participant UI as React client
    participant API as Authenticated API
    participant Store as PostgreSQL
    participant Workflow as Native MAF workflow
    actor Reviewer
    Submitter->>UI: Sign in and submit case
    UI->>API: Authorized submission with idempotency key
    API->>Store: Persist case
    API->>Workflow: Start; pause for decision
    Reviewer->>UI: Sign in and review case
    UI->>API: Approve or reject
    API->>Store: Authorize and persist decision
    API->>Workflow: Resume matching request
    alt Approved
        Workflow->>Store: Commit permitted database action and ledger
    else Rejected
        Workflow->>Store: Record workflow completion without action
    end
```

The action is only permitted on approval; rejection does not authorize it.
This diagram summarizes the local flow, not a verified live Entra session.
Authorization failures, duplicate requests and recovery are addressed in
[specifications](specs.md) and [tests](../testing.md). The reviewer must be
distinct from the submitter.
