# Issues, Fixes, and Changes

This log records significant implementation and deployment corrections together
with their evidence and remaining validation gaps. An entry does not change a
plan or release status unless the corresponding validation is complete.

## 2026-11-27 - PR #62 development POC deployment

Status: **Development POC deployed; validation partial**. The deployment plan
remains **Approved / Not Validated**, PR #62 remains draft, and production
readiness is not claimed.

### Hosted-agent startup failure

- **Issue:** Foundry hosted-agent version 10 failed before application
  initialization. Its session log reported
  `PermissionError: [Errno 13] Permission denied:
  '/home/session/.agentserver'`.
- **Cause:** Foundry set `HOME=/home/session`, while the non-root image user
  owned `/home/hosted`. AgentServer derived its default file-backed state root
  from `HOME` and could not create the required directories.
- **Impact:** The first ORS-001 case was created, but the API did not receive an
  acknowledged Foundry start within the bounded timeout and recorded
  `AmbiguousCreate`. That case was not replayed.
- **Fix:** Set
  `AGENTSERVER_STATE_ROOT=/home/hosted/.agentserver` in a permission-only image
  layer based on the verified version-10 image digest. Local construction with
  Foundry's `HOME=/home/session` override completed without filesystem errors.
  The corrected immutable image was pushed as
  `sha256:278843a486038c230c78bd658bd1e1a9a59a8c3c40f05dcdbafbd9a27b07223c`.
- **Evidence:** The image was journal-published as hosted-agent version 11,
  reached `active`, and was promoted to the fixed 100% route. Final version-11
  sessions executed ORS-001 and ORS-004 successfully.
- **Historical record:** The original ambiguous version-10 case remains
  unchanged. A new authorized case was used rather than replaying its unknown
  start operation.

### Image publisher correction

- **Issue:** Foundry rejects platform-reserved variables in image-container
  definitions, including `FOUNDRY_PROJECT_ENDPOINT`,
  `APPLICATIONINSIGHTS_CONNECTION_STRING`, and
  `APPLICATIONINSIGHTS_AUTH_MODE`.
- **Fix:** Image publication filters those variables from the submitted
  container definition while retaining the complete target configuration in
  the journaled publication identity.
- **Evidence:** All 18 focused publisher tests passed. Operation
  `pr62-3cfdbd9-image-v3-homefix-20261127t1114z` acknowledged active version 11
  on the expected immutable digest while the route remained fixed to version
  10.

### Web proxy corrections

- **Issue:** The generated web proxy first targeted the Docker Compose hostname
  `api:8000`; the initial Azure HTTPS correction then forwarded the public web
  hostname to the API upstream and returned HTTP 502.
- **Fix:** The deployed web revision uses the API HTTPS FQDN, TLS SNI, and the
  upstream host header.
- **Evidence:** Revision `aborsfoundpv2n45-web--pr62-3cfdbd9-v3` is healthy at
  100% traffic; the root, health endpoint, and authenticated proxied API path
  returned their expected responses.
- **Remaining gap:** The deployment-portable nginx correction is not yet
  represented in the repository-generated web configuration.

### Final authorized scenario results

- **ORS-001:** completed; one claim, one effect, one terminal event.
- **ORS-004:** completed idempotently; original outcome returned, one effect,
  and no duplicate terminal event.
- **ORS-006:** failed explicitly with `policy_evidence_missing`; zero effects
  and one terminal event.
- **ORS-007:** failed explicitly with `policy_evidence_conflict`; zero effects
  and one terminal event.
- **ORS-008:** the digest-invalid, expired, and non-applicable variants all
  failed explicitly with `policy_evidence_invalid`; each had zero effects and
  one terminal event.
- **Remaining gaps:** ORS-002, ORS-003, ORS-005, and ORS-009 were not run.
  Seven Azure Policy audit findings remain unresolved. The evidence is for a
  development POC only.
