# Copilot instructions

- Treat this as a public repository. Do not add credentials, customer data,
  tenant-specific configuration, private evidence, or copied scenario-specific
  code. Preserve required license notices when reuse is explicitly approved.
- Phase 1 currently covers a synthetic scenario, acceptance tests, and local
  readiness validator. Do not create the application or Azure resources
  without an explicit request and required authorization.
- Keep blueprints framework-native and independently deployable. Do not add a
  shared runtime dependency or conflate conversation, framework checkpoints,
  business state, and human approval.
- Protected public endpoints still require authentication and authorization.
  Keep model/tool input untrusted, side effects idempotent, and logs
  privacy-safe. Never silently replace failed model calls with synthetic output.
- Map significant requirements to checks and evidence; label assumptions and
  unverified claims. Do not weaken, skip, or relabel failed or unverified
  checks. Prototype readiness may disclose non-blocking failures; production
  requires verified, scoped human risk acceptance for them. Critical and
  security-critical checks cannot be silently downgraded or waived.
- For each meaningful PR, update `docs/master-checklist.md`,
  `docs/implementation-plan.md`, and relevant architecture documentation.
  Record acceptance criteria, evidence or a PR link, and the next action; mark
  work completed only when implemented and supported by evidence. Preserve the
  supplied architecture HTML's historical design and annotate current status
  when its revision is explicitly requested.
- Keep proposed schema versions and synthetic examples consistent. Schemas do
  not authenticate people, verify artifacts, or enforce cross-file traceability;
  do not represent schema validation as a release gate. The validator requires
  independent trust and cannot prove real-world identity or test execution.
  Future producer metadata belongs under `extensions` and cannot override
  required contract semantics.
- Run `python -m unittest discover -s tests -v` after contract changes, in an
  isolated environment with `requirements-dev.txt` installed. CI must remain
  usable on GitHub-hosted runners without Azure credentials.
