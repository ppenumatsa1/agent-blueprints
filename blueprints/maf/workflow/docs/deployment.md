# Deployment design

The only currently runnable deployment configuration is the loopback
[Compose prototype](../compose.yaml); it is not a production topology.
API and PostgreSQL ports are not published, the web port is loopback-only,
and `/healthz` is unauthenticated and contains no business data. Protected
API operations require authentication and case authorization. See
[setup](setup.md) for existing identity prerequisites and volume handling.

**Implemented, locally verified application boundary:** hosted mode requires
an integrated Agent A Responses `WorkflowHost` adapter. There is deliberately
no default HTTP transport: the API does not expose or call invented `/runs`
or `/operations` routes. Missing integration fails startup. Agent A's native
client creates Foundry conversations and Responses operations with
`store=true`, `background=true`, and structured `function_call_output`.
Foundry owns execution and checkpoint/session bytes; PostgreSQL stores only
business state, caller/session/conversation binding, and opaque operation
correlation.

The hosted implementation has local PostgreSQL contract evidence only. Agent
A must authenticate the API UAMI, use the Foundry scope, inject its durable
Responses adapter, and use its separate hosted execution identity. No
Azure-hosted agent, API, UI, database, or RBAC path is proven by this
repository change.

**Implemented, offline only:** [staged Foundry-first Bicep and azd
descriptors](../infra/README.md), managed identity resources, and
credential-free compilation, lint and configuration tests. Optional model,
project-wide API grant, registry and API/UI Container Apps default off. No
hosted-agent service is declared. These definitions are not an end-to-end
deployment and establish no live identity or network behavior.

**Implemented, locally verified configuration:** runtime supports on-demand
Azure PostgreSQL managed-identity tokens or a secret-manager password,
`verify-full` TLS, bounded connections with expiring lifetimes, explicit
schema-owner migrations, and startup head validation. Runtime and migration
URLs are separate. **Still unverified live:** usable cloud network paths,
database Entra roles/grants, certificate validation, backup/restore, failover,
and deployment automation. The staged database
selects PostgreSQL 16, while local Compose uses 17. A separate migration
revision passed 12 tests against local PostgreSQL 16.15, but
[integrated target-version and Azure verification](../infra/README.md#open-postgresql-version-gap)
is still required. There is no supported
provisioning or deployment command in this project. Before any authorized deployment,
verify service/version compatibility, authentication, authorization, network
exposure, secret delivery, database access and migrations, checkpoint
ownership, recovery, image publication, least-privilege permissions, backup,
retention, monitoring, cost and teardown ownership. Public endpoints still
require authentication and authorization. Foundry and monitoring public
access are disabled, but their private connectivity is not supplied.
Deployment and resource creation require separate authorization.
