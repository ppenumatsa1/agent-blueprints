# Engineering standards

These are requirements for future blueprints, not claims that Phase 0 already
implements them. A customer project must own and verify its own application,
dependencies, infrastructure, evidence, and operations.

## Trust and data

- Treat requirements, retrieved material, model output, and tool responses as
  untrusted input. They cannot change system instructions, authorization,
  verification criteria, or approval decisions.
- Require authenticated identities and server-side authorization for protected
  APIs, business records, tools, and approvals, including on public-network
  endpoints. Derive the actor from validated identity, not request-body claims.
  Use least-privilege managed identities for supported service-to-service
  access and an explicit CORS origin allowlist.
- Keep secrets out of source, images, logs, examples, browser bundles, and
  pull-request artifacts. Use approved secret stores and rotation procedures.
  Never commit customer data or tenant-specific settings to this public repo.
- Constrain tools by purpose, permissions, input validation, timeouts, and
  resource limits. Destructive or consequential actions require an authorized
  human decision and server-side enforcement; a model recommendation is not
  approval.
- Design data classification, residency, retention, deletion, and access
  controls before processing real customer material. Use synthetic data for
  shared examples and CI.

## Correctness and recovery

- Use the framework's native workflow or harness primitives. Keep conversation,
  workflow checkpoints, business records, and audit history distinct.
- Bind state and execution to the authenticated user and request. Persist
  approval and idempotency records durably; enforce uniqueness and handle
  concurrent or repeated requests without duplicate side effects.
- Test pause/resume, rejection, retries, cancellation, restart, and recovery.
  A fallback host is an explicit, reviewed deployment choice, not a silent
  switch after an error.
- Report actionable errors; use bounded timeouts and retries where safe.
  Synthetic or offline mode must be explicitly selected and must not hide a
  failed model, authorization, or deployment call.

## Evidence, tests, and observability

- Map significant requirements to checks, implementation references, and
  revision-specific evidence. Schema validity alone is not release readiness.
- Use focused unit and contract tests, integration tests against real
  boundaries, end-to-end tests, and agent evaluations appropriate to each
  requirement. Set evaluation datasets, rubrics, and thresholds before accepting
  results; cover negative, adversarial, and failure cases.
- Capture privacy-safe traces, request and workflow correlation, errors,
  latency, model/token usage, and cost where available. Redact by default;
  protect access and retention. Verify exported telemetry rather than assuming
  a configured exporter works.
- Record known gaps, ownership, decisions, and human-approved exceptions
  without silently weakening any applicable evidence requirement. The
  [readiness contract](readiness-contract.md) defines the evidence states.

## Supply chain and GitHub security

- Pin and review dependencies and GitHub Actions, keep dependency manifests
  current, and evaluate vulnerability, license, and provenance findings. The
  current CI validates contracts, the local validator, and golden fixture
  structure; the application acceptance adapter is not implemented. CI is not
  a security scan or an application deployment. Its validator dependencies and actions are
  pinned, but transitive Python dependencies are not locked.
- GitHub offers [secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning),
  [Dependabot alerts](https://docs.github.com/en/code-security/dependabot/dependabot-alerts/about-dependabot-alerts),
  and [code scanning](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning)
  for eligible public repositories, subject to current account, repository,
  and product settings. Confirm availability and permissions before relying on
  a feature; do not enable paid features without authorization.
- On 2026-11-20, the public repository API reported secret scanning and push
  protection enabled, Dependabot security updates disabled, and CodeQL default
  setup not configured. The vulnerability-alerts endpoint reported alerts
  disabled. These are point-in-time settings, not proof that all secrets or
  vulnerabilities are detected; recheck them before relying on them.
- This repository and the inspected reference repositories use the MIT
  License. Consult each project's own license and preserve applicable notices
  if code is copied; third-party dependencies may have different terms.
