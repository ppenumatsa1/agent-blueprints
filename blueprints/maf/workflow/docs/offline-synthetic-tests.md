# Operator-triggered offline synthetic manual tests

This is a fixed, disposable test of the bundled native MAF approval workflow,
not a browser capability, application sandbox, approval exception, or release
gate. Production authorization, separation of duties and business execution
are unchanged. Do not send customer data, credentials or application code.

From the blueprint or independently generated project root, with Python 3.12
and an operator-owned local Linux Docker engine using default seccomp:

```text
python scripts/run_synthetic_manual_test.py
python scripts/run_synthetic_manual_test.py --decision approved
python scripts/run_synthetic_manual_test.py --decision rejected
```

Default execution runs both decisions in separate containers. The operator
selects only the bundled decision; there is no code, payload, callback, image,
endpoint or application-factory parameter. The graph is the canonical
`backend/app/workflows/workflow.py`, using native `WorkflowBuilder`,
`request_info` and `Workflow.run(responses=..., stream=True)`. It must suspend
once before the supplied boolean response, produce the exact decision output,
and record exactly one fixed synthetic case in process memory. The fixture
does not call a business action. Synthetic approval is **not human approval**.

## Enforced execution boundary

The host launcher uses a temporary build context containing only its explicit
file allowlist: dependency lock/verification inputs, the canonical workflow
and domain types, package markers, the fixed runner, Dockerfile and MIT notice.
It does not upload the repository, `.env`, application factories, infrastructure
implementations, scenario adapters, checkpoints or Docker credentials.
Dependencies use the existing lock hashes and approved framework-wheel check.
The image retains dependency distributions, but not application implementations.

Builds require network access to public image/package registries. If a
corporate network blocks the default Python index, `--package-index` accepts
an operator-trusted HTTPS mirror without URL credentials or query parameters;
lock hashes and TLS validation remain required. This is a build-only setting,
not a runtime endpoint. The base image tag follows the blueprint's existing
`python:3.12-slim` convention; it is not immutable source-to-image attestation.

The selected Docker context must resolve to a local Unix socket or local
Windows named pipe. Its endpoint is pinned for the process; caller
`DOCKER_HOST`/`DOCKER_CONTEXT` overrides are not forwarded. A local socket
forwarded to a remote daemon cannot be detected: the operator must own and
trust the host, Docker configuration, daemon, base image, dependencies and
reviewed source. Docker/OS administrators can bypass these controls. This is
not isolation from malicious host administrators or a general hostile-code
sandbox. Run only the reviewed bundled code.

Before starting, the launcher inspects the actual container and fails closed
unless it matches the fixed immutable image ID, entrypoint, decision and
runtime policy. It requires network `none`, a read-only root filesystem,
UID/GID 65534, all capabilities dropped, no-new-privileges, private IPC, no
user mounts/volumes/devices/extra hosts/ports/stdin, and fixed CPU, memory, process
and log limits. It rejects credential environment keys and modified commands.
The isolated Python entrypoint ignores Python environment configuration and
clears its environment before importing the workflow. No Docker socket or
application credential directory is provided.
Docker's normal private `/proc`, `/dev` and shared-memory system mounts remain;
there is no supplied writable persistent volume or application checkpoint.

Before the native graph runs, runtime probes require no external interface,
no effective capabilities, no-new-privileges and active seccomp; writes under
`/offline`, `/tmp` and `/home` must fail as read-only. TCP connection attempts
to a documentation-only external address and the metadata address must fail
with no route. Application/runtime assets and Docker socket paths must be
absent, and the root credential directory must be absent or inaccessible.
These are negative checks in addition to kernel-enforced restrictions, not a
flag or callback declaration. A probe/decision failure yields no successful
result. Start has a 60-second host deadline; the container is force-removed in
`finally`, including on a timeout or inspection failure. Docker failure or
host termination can still prevent cleanup. Images/build cache remain local;
there is no automatic broad Docker cleanup.

## Evidence and limits

```text
python -m unittest discover -s scripts/tests -v
```

These explicit tests require real Docker; unavailable Docker is a failure,
not a skip. They build the image, exercise native approval/rejection and
runtime denial probes, inject inert caller credential/application canaries,
and verify that actual network, writable-root, root-user, tmpfs, credential
environment and entrypoint alterations are rejected **before** Docker start.
The repository's `tests/test_synthetic_manual_test.py` also checks the
allowlisted build context, symlinks, remote endpoints, resource/capability
mutations, timeout cleanup, and absence of success on denied inspection.
CI repeats real Docker checks in independently instantiated base and Order
Resolution projects while the source checkout is temporarily unavailable.
The profile's domain workflow is intentionally **not** loaded by this runner.

Output is JSON explicitly marked `offline-synthetic-native-approval`,
`business_effects: 0` and `durable: false`. It is only evidence about this
fixed local graph/fixture and its tested container configuration. No model,
PostgreSQL, Azure, Entra, business effect, application-supplied workflow,
durable checkpoint/recovery, atomic exception audit, browser integration or
production readiness is tested or claimed. Application-supplied studio
manual-test callbacks remain disabled. Secure browser dispatch and any
same-identity exception remain unimplemented and require separate design,
authorization and evidence.
