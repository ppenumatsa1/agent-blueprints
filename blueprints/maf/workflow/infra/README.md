# Foundry-first infrastructure: offline preparation

These Bicep modules and `azure.yaml` are **staged infrastructure**, not a
deployable end-to-end application or authorization to create resources.
Nothing in this directory has been provisioned or tested against Azure.
The host adapter, API-to-agent protocol, identity propagation, approvals,
managed checkpoints and recovery remain unverified. The Foundry hosted-agent
service is deliberately absent from `azure.yaml` until its actual source
root, entrypoint and contract are agreed. The two declared Container Apps
services are the adjacent API and web UI, **not** workflow runtimes.

```mermaid
flowchart LR
  Browser[Browser] -. authenticated path not yet wired .-> UI[ACA UI - opt-in]
  UI -. protected API path not yet wired .-> API[ACA API - opt-in]
  API -. project-scoped agent consumer .-> Foundry[Foundry project]
  Foundry -. hosted workflow interface unverified .-> Agent[Hosted native workflow]
  API -. private network and Entra DB auth unverified .-> DB[Private PostgreSQL]
  API -. export and network unverified .-> AI[Application Insights / Log Analytics]
```

Solid IaC resources do not establish the dashed runtime connections. Foundry
network access and telemetry ingestion/query are disabled, with **no** private
endpoints or Azure Monitor Private Link Scope in this milestone. They will
not be reachable until a separately reviewed network path is supplied. The
current local API only accepts `WORKFLOW_HOST=local` and does not implement a
managed-identity PostgreSQL token flow; do not run it as the intended cloud
API. The current nginx proxy targets `api:8000`, whereas ACA HTTP ingress uses
its own TLS endpoint, and the SPA needs its public Entra values at build
time. These are integration blockers, not configuration defaults to guess.

## What the modules describe

| Module | Behavior and limitations |
| --- | --- |
| `network.bicep` | One parameterized RFC1918 VNet; separate delegated ACA and PostgreSQL subnets; PostgreSQL private DNS zone and link. No Foundry/monitor private endpoints, NSGs, egress filtering or production network controls. |
| `foundry.bicep` | Foundry account and project with system identities, key authentication disabled, public access disabled and deny-by-default ACLs. A model deployment is opt-in and requires a reviewed model, version, SKU, capacity, region and quota. |
| `postgres.bicep` | Private Flexible Server and database, Entra-only auth, an explicitly supplied administrator, TLS required, 7-day backup and development-sized burstable default. No password administrator, firewall allow-all, database application principal or token-refresh implementation is created. |
| `observability.bicep` | Workspace-based Application Insights and Log Analytics, 30-day default retention and 1 GB/day ingestion cap. Public ingestion/query and Insights local authentication are disabled; no private connectivity or exporter role is configured. The cap can discard telemetry. |
| `identities.bicep` | Separate API and UI user-assigned managed identities. The project system identity receives Foundry User at account scope per the Foundry guidance; the API identity receives Foundry Agent Consumer at project scope. These assignments and actual data-plane requirements need live review. |
| `registry.bicep` | Optional Basic registry. It is internet-reachable when selected, but disables admin credentials and anonymous pulls; the two workload identities get only registry-scoped AcrPull. Private registry networking and hosted-agent image-pull permissions are not implemented. |
| `container-apps.bicep` | Optional, separate UI and API in an internal-only workload-profile environment, with HTTPS-only internal ingress and scale-to-zero. Entra authentication returns 401 on the API except for `/healthz`; the API must still enforce scopes, roles and record authorization. Caller-supplied images and configuration are required. |

`createRegistry`, `createContainerApps`, and `deployModel` default to false.
Creating the template's other resources would still incur cost, especially
PostgreSQL; the defaults are development-oriented, not free and not a
production availability, backup, security or cost claim. Availability,
retention, networking and pricing require a separate regional review.

The deployment principal needs permission to create the requested resources
and scoped role assignments. Runtime roles must not be used as provisioning
permissions. `apiEnvironment` and `webEnvironment` are **non-secret** only.
For application secrets, `apiSecretReferences` accepts entries with `name`,
`keyVaultUrl`, and `environmentName`; an existing vault and a separately
authorized Key Vault Secrets User assignment for the API identity are
prerequisites. Neither the vault nor that assignment is provisioned here.
Never put credentials, tokens, passwords or connection strings in parameter
files, environment examples, outputs, images or logs. Current backend/DB
authentication still needs a compatible implementation; a secret reference
does not make the Entra-only database compatible.

`main.parameters.json` binds only required non-secret values to azd
environment variables. `environments/azd.env.example` and the two
`.bicepparam` examples contain synthetic placeholders; they are not usable
Azure configuration and do not select a subscription, region or tenant.
The `.bicepparam` files are compiler examples, not automatically selected
by azd. Optional Bicep parameters require explicit, reviewed native-typed
parameter values; model and image inputs must not be invented.

## Credential-free checks

From the blueprint root, or from a generated project's own root:

```text
python infra/validate.py --check-compiler
python infra/validate.py
python -m unittest discover -s infra/tests -v
```

Python 3.12 and Bicep 0.49.2 or newer are prerequisites. If `bicep` is not on `PATH`, the
checker also searches the Azure CLI's cached binary, or accepts an explicit
`BICEP_CLI` path. It does not install dependencies, use Azure credentials,
restore external modules or make network requests. CI installs a compiler
only when this prerequisite check fails. The checker compiles and lints the
local Bicep graph, compiles both parameter examples, checks the committed
network examples, and validates local service paths and required azd
bindings. Tests additionally inspect compiled ARM security properties and
exercise negative configuration cases. These checks do **not** evaluate
arbitrary future operator-supplied parameters or prove Azure compatibility.

The modules use local Bicep resources rather than external registry modules,
so offline validation and generated copies do not depend on AVM downloads.
This is not a claim that the modules are Azure Verified Modules. The compiler
and linter cannot establish quota, SKU availability, role propagation, live
authentication, private DNS or network reachability, secure image pulls,
telemetry delivery, hosted-agent behavior, checkpoints or business recovery.

Before any deployment, integrate and test the actual Foundry host contract,
database authentication, reverse proxy and UI build; review network, roles,
secrets, logging and image provenance; then prepare the required inventory,
cost estimate and approval. A future live test must record real outcomes,
including failures. No Azure resource mutation is authorized by these files.
