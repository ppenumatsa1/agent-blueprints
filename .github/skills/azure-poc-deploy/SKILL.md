---
name: azure-poc-deploy
description: Deploy and verify the Order Resolution development POC on existing Azure resources. Use when explicitly asked to deploy this POC or run its Azure end-to-end scenarios without provisioning infrastructure.
---

# Azure Order Resolution POC deployment

Use this workflow only for an explicitly authorized development deployment.
Creating or reviewing this skill does not authorize deployment. Follow applicable
higher-priority instructions and other mandatory requirements; if they
conflict with this existing-resource-only scope, stop and report the exact
source and the authorization or guidance change needed. Never relabel a failed
or unverified check as passed or mark a plan Validated without its required
validation.

## Scope and safeguards

- Use only the authorized existing subscription, registry, PostgreSQL database,
  Foundry project and agent, and Container Apps. Never run `azd provision`,
  provision infrastructure, or modify Azure Policy, firewall rules, networking,
  Entra configuration, managed identities, or unrelated resources.
- Preserve existing Container Apps secrets and references; never print or log
  their values, credentials, or tokens. Keep self-approval disabled and do not
  create self-decision grants to run the selected cases.
- Prevent unauthorized side effects using verified controls. Old development
  sessions are disposable, but routing new requests to a new version alone
  does not fence callbacks from older sessions. Do not resume or inspect old
  sessions individually unless necessary. Stop if an actual unauthorized
  side-effect risk cannot be controlled within the authorized scope.
- Record the seven existing Azure Policy audit findings as unresolved and
  deferred; do not claim they passed or changed. Keep the PR draft and unmerged.

## Execute

1. **Verify the target and candidate.** Confirm the subscription and all
   existing resource identities against the user's authorization. Verify the
   intended commit SHA matches the PR head, the source used to build, and the
   exact-head CI results. Confirm required Azure and database permissions
   without expanding runtime API privileges. Read the database migration state
   and schema; if required migrations are absent, apply only the authorized
   forward migrations as an existing schema owner with bounded lock and
   statement timeouts. Stop on schema drift or an uncertain result and inspect
   the actual state before any forward retry.
2. **Publish immutable images.** Build or verify the API, web, and hosted-agent
   images from that exact candidate. Preserve the deployed web's Entra build
   settings and HTTPS API upstream. Push only to the existing authorized
   registry, compare push digests with registry manifest metadata, and use
   digest references rather than mutable tags. Do not treat a local image ID
   as a registry digest or a digest alone as proven build provenance.
3. **Publish and pin the hosted agent.** Read the existing agent route and
   serving version. Before publishing behind `@latest`, pin the existing route
   to its concrete version at 100%, preserving other endpoint settings and
   coordinating writers. Use the repository's journaled publisher and verify
   the new version's configured image, identity, access, and active state. Do
   not replay an ambiguous publish. Confirm the new version has the existing
   required access without changing identities or Entra assignments.
4. **Update existing apps.** Before each scoped API or web update, privately
   snapshot both apps' secret values or references, identities, configuration,
   networking, and unrelated settings. Use a verified update payload that
   excludes secret configuration and identity. Immediately compare after each
   update without exposing sensitive data; stop on unexpected changes. Set
   the API's concrete hosted version, source/deployment revision, and
   `ORDER_RESOLUTION_POC_SELF_DECISION=false`. Verify the observed image digests,
   revisions, route, health, and preserved settings.
5. **Run synthetic Azure E2E.** Execute ORS-001, ORS-004, ORS-006, ORS-007,
   and all ORS-008 variants with authorized identities. Start with ORS-001.
   If the driver unnecessarily requires a separate reviewer for these
   non-approval cases, narrowly fix it and run affected tests; do not weaken
   authorization or enable self-approval. Capture sanitized actual API
   responses, database evidence, Foundry execution traces, and individual
   pass/fail results. Mark missing evidence unverified; leave ORS-002,
   ORS-003, ORS-005, and ORS-009 pending.

Stop for actual permission, safety, or technical failures. Report the exact
failure, evidence, and minimum corrective action; do not silently retry
ambiguous side effects. Report deployed resource revisions, image digests,
agent version, secret-preservation results, each case outcome, and remaining
gaps. Do not infer production readiness from a development POC.

## References

- `docs/azure-foundry/hosting.md` describes the existing image publisher,
  fixed-route precondition, and ambiguous-operation recovery.
- `profiles/order-resolution/overlay/backend/tests/live_acceptance.py` and the
  canonical Order Resolution scenarios define the live evidence and cases.
- Consult Microsoft Learn for current
  [Container Apps secret](https://learn.microsoft.com/azure/container-apps/manage-secrets)
  and [revision](https://learn.microsoft.com/azure/container-apps/revisions)
  behavior. For additional documentation, use Microsoft Learn MCP search,
  fetch, or code-sample search. If unavailable, use `npx @microsoft/learn-cli`
  with `search`, `fetch`, or `code-search`, respectively.
