# Synthetic POC self-decision

This is not a production feature or permission to deploy. In the generated
hosted profile, both the API and Agent A default
`ORDER_RESOLUTION_POC_SELF_DECISION` to off. Leave it off outside the reviewed,
dedicated synthetic POC. Do not copy its `ors_poc` schema to another database.

## Database owner setup

Only the existing Entra PostgreSQL owner may install `self-decision.sql` after
the normal profile migrations. Use `psql` with a short-lived access token for
`https://ossrdbms-aad.database.windows.net`, verified TLS, and the exact POC
database, not the administrative `postgres` database. Pass these `psql` variables:

| Variable | Value |
|---|---|
| `database_host` | Exact verified PostgreSQL POC DNS name |
| `runtime_role` | Existing API PostgreSQL managed-identity role name |
| `tenant_id` | Entra tenant UUID |
| `identity_oid` | Existing API managed identity's **principal object ID**, not its client ID |
| `operator_oid` | Existing Entra PostgreSQL administrator and API operator's user object ID |

Use the unshared POC role and verify that the human owner has authority over
the migrated case, proposal and decision tables. The installation is
transactional and intentionally refuses to replace any existing scope. It
adds no public schema DML grants. It validates the Azure-managed Entra role
labels in the cluster-wide PostgreSQL catalog, not the database-local Entra
administration functions. Confirm the application database exposes the
exact service and human-admin labels before enabling either workload. The API
must use the exact host and
configured user-assigned managed identity via the Container Apps MI endpoint
and verified TLS. Never substitute a developer credential for the API.

## Decide an exact pending synthetic case

Once activation is separately authorized and verified, submit an
approval-required synthetic order with the operator as reviewer. Wait for the
native hosted approval handle. Using the same signed-in Entra user, from the
generated backend run:

```text
python -m app.order_resolution.poc_grant --database-url "<passwordless PostgreSQL URL with sslmode=verify-full and sslrootcert=system>" --case-id "<case UUID>" --proposal-version 1 --handle-digest "<SHA-256 of exact native handle>" --action "<proposal action>" --destination-id "<synthetic destination>" --decision approved
```

Use `--decision rejected` for rejection. The command acquires the PostgreSQL
token through Azure CLI without putting the token in arguments, files, or
output. PostgreSQL verifies the issuer's exact Entra administrator mapping
against the protected operator scope. It grants only this pending proposal,
payload, digest, and outcome; a grant expires within five minutes and cannot
outlive the native handle. The same grant can be retried while pending;
changing the outcome or renewing an expired grant is not permitted by the
command. Then submit the matching authenticated API decision. The API's
`workflow.read`, `workflow.write`, and `workflow.approve` scopes and
`Acceptance.Operator` and `Workflow.Approver` roles must be available to the
operator; these checks are not satisfied by the PostgreSQL token.

The golden live driver uses this grant path only when
`MAF_LIVE_POC_OWNER_DATABASE_URL` is explicitly set. ORS-002 and ORS-003 take
the same-identity path; cases not needing a decision use a reserved reviewer
placeholder that is not an Entra user and cannot approve. Do not claim a case
requiring multiple distinct principals from this single-identity mode.

Inspect `ors_poc.decision_audit` as the database owner. The protected audit
append and durable decision are atomic. An approved effect is restricted to
the built-in PostgreSQL synthetic destination and requires the matching audit;
rejection performs no effect. This is not a substitute for deployment
provenance, independent evidence of the human token, or defense against the
trusted database owner. Direct writes to existing business and synthetic
tables are not authoritative proof of an exception. Disabling both workload
options restores the usual distinct-identity restriction; retain the
protected database audit as evidence.

Do not roll back an API binary while any self-reviewed POC case, issued grant,
approved decision, queued effect, or hosted session remains reachable by that
binary. A historical API version rejects *new* self-decisions but can process
an already persisted self-approval without this protected grant check.
Quiesce and account for all such cases, work queues, and running sessions
before a binary rollback; a clean publication journal or reverting a Foundry
route alone does not establish safety. This isolation has not been verified
in Azure. Keep activation blocked pending an authorized security review.

Platform references: [Azure Entra role labels](https://learn.microsoft.com/azure/postgresql/security/security-manage-entra-users#enable-microsoft-entra-authentication-for-an-existing-postgresql-role-using-sql)
and [PostgreSQL shared roles catalog](https://www.postgresql.org/docs/17/catalog-pg-shseclabel.html).
