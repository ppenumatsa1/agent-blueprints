# Engineering journal

## Migration review revision

- **Change:** validate version-specific manifests and separate explicit
  schema-owner migration from read-only runtime validation. The synthetic
  example has a separate operator preparation command.
- **Local evidence:** `python -m unittest -q tests.test_core
  tests.test_security tests.test_evidence_runner tests.test_modularity
  tests.test_migrations` passed 44 tests each in the source and an independent
  generated copy on isolated PostgreSQL 17; the focused migration suite
  passed 12 tests, including a test-only second
  revision, restart, data preservation, drift, rollback, concurrent startup,
  and a role without database/schema CREATE privileges. Generator tests
  passed 2 tests. Local Compose migration/preparation/startup and generated
  image build passed with a locally selected package proxy. These are
  synthetic local results, not release approval.
- **Fix during verification:** the first Compose preparation attempt failed
  because its executable module imported `os` too late. The import was fixed,
  a subprocess regression added, and Compose preparation passed on rerun.
- **Constraints:** no automatic baseline downgrade; migration requires a
  reviewed schema-owner operation and consistent backup. Catalog formatting
  on other PostgreSQL versions is unverified.
- **Next:** reconcile the parallel foundation's canonical import/alias removal,
  dependency tooling and documentation overlap, then rerun relevant checks
  and actual credential-free PR CI against the integrated head. Hosted
  identities, live restore and deployment are unverified.
