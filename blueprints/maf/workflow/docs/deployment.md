# Deployment design

The only implemented deployment configuration is the loopback
[Compose prototype](../compose.yaml); it is not a production topology.
API and PostgreSQL ports are not published, the web port is loopback-only,
and `/healthz` is unauthenticated and contains no business data. Protected
API operations require authentication and case authorization. See
[setup](setup.md) for existing identity prerequisites and volume handling.

**Planned, unverified:** a Foundry Hosted Agent using a compatible native MAF
Responses integration and host-managed checkpoints, with separate API and UI
hosting; an ACA-hosted workflow is a distinct alternative requiring its own
compatible multi-replica-safe checkpoint strategy. Neither path is implemented
or proven here. Do not mount local file checkpoints as a substitute for a
host-managed provider.

**Planned, unimplemented:** Bicep/azd infrastructure, managed identities,
resource bindings and deployment automation. There is no supported provisioning
or deployment command in this project. Before any authorized deployment,
verify service/version compatibility, authentication, authorization, network
exposure, secret delivery, database access and migrations, checkpoint
ownership, recovery, image publication, least-privilege permissions, backup,
retention, monitoring, cost and teardown ownership. Public endpoints still
require authentication and authorization. Private networking is not implied.
Deployment and resource creation require separate authorization.
