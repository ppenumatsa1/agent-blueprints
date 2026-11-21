# Behavioral specifications

1. Reject unauthenticated or unauthorized protected operations; authorize
   each case and require a reviewer distinct from the submitter.
2. Record an authorized decision durably before resuming the matching
   workflow; serialize conflicting decisions.
3. Use a case-scoped lock and reconcile database state and native file
   checkpoints after interruption. Never assume they are one atomic store.
4. Commit the local database action with its ledger entry; external actions
   need downstream idempotency or a transactional outbox.
5. Treat model/tool input as untrusted; never silently replace a failed
   model or tool call with synthetic output.
6. Preserve failed and unverified evidence outcomes. An unsigned synthetic
   result or a valid schema is not an authorized release.

The [testing guide](../testing.md) identifies current local checks and
limitations. The API's [implementation](../../backend/app/api.py) and
[core tests](../../backend/tests/test_core.py) are authoritative for
implemented behavior; this document is not a separate release gate.
Production operation, live identity and hosted recovery require separate
verification.
