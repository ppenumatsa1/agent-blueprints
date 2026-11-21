# Product requirements

## Purpose and scope

Provide an independently owned, framework-native MAF workflow project that
can accept a case, pause for an authorized human decision, and resume a
bounded action with recoverable local state. The included application and
verification scenario are synthetic examples, not customer business logic.
See the [project guide](../../README.md).

## Users and requirements

| User | Requirement | Current evidence and limit |
| --- | --- | --- |
| Application developer | Own rules, policy, workflow and action without a shared runtime dependency. | [Extension guide](../architecture.md); application-specific security remains the developer's responsibility. |
| Submitter and reviewer | Authenticated case submission and an authorized decision by a distinct reviewer. | Backend and UI tests use synthetic identity; real Entra sign-in is unverified. |
| Operator | Persist decisions, recover local workflow interruptions and avoid repeated database effects. | Core tests cover both worker-kill windows; external side effects require independent idempotency. |
| Assessor | Preserve evidence, failure and unknown outcomes for an independent readiness assessment. | Copied verifier and synthetic fixture; independently authorized approval and trust are outstanding. |

Production readiness, live hosted recovery, agent evaluations and cloud
deployment are not established. A completed prototype test does not authorize
a consequential action or a release. See [specifications](specs.md) and
[deployment flow](deployment-flow.md).

## Design index

[Technology stack](techstack.md) · [Specifications](specs.md) ·
[Architecture](architecture.md) · [Project structure](projectstructure.md) ·
[User flow](userflow.md) · [Deployment flow](deployment-flow.md) ·
[Issues and changes](issues-changes-fixes.md) ·
[Engineering journal](../engineering-journal.md)
