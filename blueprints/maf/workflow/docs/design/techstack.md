# Technology stack

| Component | Current local implementation | Boundary |
| --- | --- | --- |
| Workflow | Microsoft Agent Framework native workflow and file checkpoints | Persistent private single-host storage, not hosted durability. |
| API | Python 3.12, FastAPI, Uvicorn, Entra token validation | Protected operations also require case authorization. |
| UI | React, TypeScript, Vite, MSAL | Public configuration only; no server secrets in the browser. |
| Persistence | PostgreSQL, psycopg, startup schema initialization | Business records, decisions, audit and action ledger; no versioned migrations yet. |
| Local hosting | Docker Compose, nginx | Loopback prototype, not a production deployment. |
| Tests | Python unittest, Vitest and copied readiness verifier | Synthetic identities and fixtures; no live Entra or cloud evidence. |

Exact dependencies are in [backend requirements](../../backend/requirements.txt)
and [frontend package manifest](../../frontend/package.json). The current
installation uses requirements files and npm. uv/Ruff, migrations,
OpenTelemetry/Azure Monitor, Foundry hosting and Bicep/azd are planned
separate work, not capabilities supplied by this baseline.
