# Deployment and validation flow

## Status boundary

**Implemented:** local development, Docker Compose, source tests, generated
project tests, and GitHub Actions on GitHub-hosted runners.

**Planned and unverified:** Bicep infrastructure, azd provisioning/deployment,
Foundry-hosted MAF, managed identity binding, Azure resource validation, cloud
telemetry ingestion, ACA alternative, and live sign-in. Explicit Azure trace
and metric exporter configuration is implemented but not cloud-verified. This document describes
acceptance gates for future work; it does not provide or authorize a cloud
deployment command.

## Local development and Compose

1. Install Python 3.12, Node 22, Docker with Compose, and an isolated
   PostgreSQL database for direct tests. Use authorized existing Entra
   registrations for interactive sign-in; registration and consent are not
   created by the project.
2. Install backend requirements from `backend/requirements-dev.txt` and run
   the targeted source suite from `backend`:

   ```text
   python -m unittest -v tests.test_core tests.test_security tests.test_evidence_runner tests.test_telemetry
   ```

3. From `frontend`, run `npm ci`, `npm test`, `npm run build`, and
   `npm run check-csp`.
4. From the project root, supply required environment variables and run
   `docker compose up --build --wait`. Only the UI binds to loopback. Review
   [setup](../setup.md) for secret handling and persistent-volume behavior.
5. Stop with `docker compose down`; volumes persist. Back up or delete data
   only under the operator's policy.

## CI and independent generation

`.github/workflows/ci.yml` (source repository) runs contract/readiness tests,
PostgreSQL-backed backend tests, frontend tests/build/CSP checks, Compose HTTP
and permission checks, and `maf-independent`. The independent job creates the
project outside the checkout, checks its own imports and build contexts, runs
generated backend/frontend/verification tests, validates evidence
disclosures, and builds the generated Compose stack. CI does not provision
Azure or prove live Entra/Foundry behavior. The generated-verifier pipeline
propagates the test command's nonzero exit through `tee` and separately
rejects skipped or expected-failure results; `tests/test_ci_workflow.py`
exercises these failure paths against the actual CI step.

Before PR approval:

1. Generate a fresh project outside the repository and verify all documentation,
   contract bytes, and imports are independent.
2. Run focused regression, security, durability, and independent checks
   affected by the change; the mandated contract-change command is
   `python -m unittest discover -s tests -v` in an isolated environment with
   `requirements-dev.txt` installed.
3. Confirm all required GitHub Actions checks belong to the exact PR head
   revision. A prior commit's green run is not evidence for a new revision.
4. Review the diff for compatibility shims, duplicate implementations,
   unused dependencies, stale paths, secrets, and unverified claims.

## Future Azure delivery gates

```mermaid
flowchart TD
    A[Local design and implementation] --> B[Static checks and generated-copy tests]
    B --> C[PR-specific CI and human review]
    C --> D{Hosting interfaces and recovery verified?}
    D -- No --> E[Stop; retain as planned and unverified]
    D -- Yes --> F[Prepare inventory, cost, identity, network, backup and rollback]
    F --> G[Explicit human authorization for Azure provisioning]
    G --> H[Reviewed Bicep/azd plan and least-privilege deployment identity]
    H --> I[Provision/deploy only after authorization]
    I --> J[Validate live auth, recovery, telemetry, smoke and rollback]
    J --> K[Record revision-scoped evidence in journal and checklist]
```

No checked-in Bicep modules or `azure.yaml` deployment path is currently
provided for this blueprint. A future Bicep/azd change must add credential-free
CI validation, scoped identity and network review, cost and teardown ownership,
and live verification. Foundry's host-managed checkpoint strategy and an
ACA-compatible strategy are distinct; neither may silently fall back to local
file checkpoints. A public endpoint must remain authenticated and authorized.

See [deployment design](../deployment.md) for the current prototype boundary
and [journal](issues-changes-fixes.md) for evidence and outstanding work.
