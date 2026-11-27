# Copilot instructions

- Treat this as a public repository. Do not add credentials, customer data,
  tenant-specific configuration, private evidence, or copied scenario-specific
  code. Preserve required license notices when reuse is explicitly approved.
- Phase 0 defines proposals, not runnable templates or deployed agents. Do not
  create later-phase implementations or Azure resources without an explicit
  request and the required authorization.
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
- For development POCs, prioritize the smallest authorized end-to-end synthetic
  cycle on the current CI-validated candidate before optional refinements.
  Freeze non-blocking improvements until that cycle is observed and fix only
  concrete blockers. Do not make retrospective unknowns or incomplete
  aspirational checks rollout gates unless needed to prevent an immediate
  safety, security, or data-integrity risk. Preserve existing explicit
  safeguards and accurately record assumptions, unknowns, failures, and next
  actions; never claim an unverified check passed.
- For each meaningful PR, update `docs/master-checklist.md`,
  `docs/implementation-plan.md`, and relevant architecture documentation.
  Record acceptance criteria, evidence or a PR link, and the next action; mark
  work completed only when implemented and supported by evidence. Preserve the
  supplied architecture HTML as the original source unless its revision is
  explicitly requested.
- Keep proposed schema versions and synthetic examples consistent. Schemas do
  not authenticate people, verify artifacts, or enforce cross-file traceability;
  do not represent schema validation as a release gate. Future producer metadata
  belongs under `extensions` and cannot override required contract semantics.
- Run `python -m unittest discover -s tests -v` after contract changes, in an
  isolated environment with `requirements-dev.txt` installed. CI must remain
  usable on GitHub-hosted runners without Azure credentials.
