# MAF workflow blueprint

This blueprint is under construction. Its native MAF workflow pauses for a
case-scoped decision and uses `FileCheckpointStorage` for local recovery.
PostgreSQL separately holds application records, decisions, audit events, and
the action ledger. No application endpoints are exposed in this core.

The workflow factory accepts a checkpoint provider from its host. The local
host uses one private directory per case; Foundry's host-managed provider and
Responses adapter are deferred to P1-12 and have not been tested here. Local
file checkpoints are restricted to one host and are not a shared-store solution.
MAF's default restricted checkpoint deserialization is retained; applications
must protect the checkpoint volume from unauthorized writes. On POSIX, the
checkpoint directories must be accessible only to the service account. On
Windows, the operator must enforce equivalent filesystem ACLs.

Business rules, the access policy, business-state repository, native workflow
construction, and the transactional action are replaceable application
components. The local host expects one request containing only `case_id` and
one matching outcome; a different native graph must preserve that contract or
provide its own host. The supplied
action in `tests` is synthetic and is not an interactive authentication mode.
An action committed in the same PostgreSQL transaction as the ledger can be
replayed safely. External side effects require their own idempotency guarantee
or a transactional outbox; this core does not claim exactly-once delivery to
arbitrary external systems.

## Core integration tests

Use Python 3.12 and an isolated PostgreSQL database. After activating a virtual
environment, install `requirements.txt` and set `MAF_TEST_DATABASE_URL` to that
database's connection string. Then run from this directory:

```text
python -m unittest -v tests.test_core
```

The suite requires PostgreSQL and fails rather than skipping when its connection
string is missing. It terminates real worker processes after decision
persistence and after the synthetic action commits, then starts new workers
against the same database and checkpoint directory. It does not establish
Foundry-hosted recovery or validate interactive Entra sign-in.
