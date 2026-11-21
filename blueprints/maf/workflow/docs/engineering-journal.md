# Engineering journal

## Migration review revision

- **Change:** validate version-specific manifests and separate explicit
  schema-owner migration from read-only runtime validation. The synthetic
  example has a separate operator preparation command.
- **Pre-rebase evidence:** source and generated backend suites passed 44
  tests each on isolated PostgreSQL 17, including a modularity test removed by
  the clean foundation. The focused migration suite passed 12 tests, including a test-only second
  revision, restart, data preservation, drift, rollback, concurrent startup,
  and a role without database/schema CREATE privileges. Generator tests
  passed 2 tests. Local Compose migration/preparation/startup and generated
  image build passed with a locally selected package proxy. These are
  synthetic local results, not release approval.
- **Fix during verification:** the first Compose preparation attempt failed
  because its executable module imported `os` too late. The import was fixed,
  a subprocess regression added, and Compose preparation passed on rerun.
- **Rebased evidence:** on foundation `61d44ed`, source and generated backend
  suites passed 43 tests each, generated verification passed 44 tests and
  generator checks passed 2. The initial verification attempt failed because
  `jsonschema` was missing; after installing the generated verifier's
  declared requirements, the 44-test rerun passed without skips. Source and
  generated Compose smokes each returned UI 200, health 204 and protected
  API 401 after explicit migration and example preparation.
- **Constraints:** no automatic baseline downgrade; migration requires a
  reviewed schema-owner operation and consistent backup. Catalog formatting
  on other PostgreSQL versions is unverified.
- **Next:** reconcile parallel dependency tooling and run actual credential-free PR CI
  against the integrated head. Hosted
  identities, live restore and deployment are unverified.
