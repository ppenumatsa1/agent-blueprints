# Development and debugging

Complete [setup](setup.md) first. Compose is the simplest integrated path;
only the web port is published. For a direct local run, use a separately
accessible PostgreSQL database, a private checkpoint directory, and set all
direct backend inputs in the launching environment. From `backend`:

```text
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

On Windows, explicitly select Python's native Selector loop for Psycopg's
asynchronous activity-stream connections, including runs without reload:

```text
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log --loop asyncio:SelectorEventLoop
```

The Windows VS Code backend launch uses the same Uvicorn option. Other
platforms retain Uvicorn's default loop selection. This does not change the
process-wide asyncio policy or replace an already running loop. An embedded
ASGI host on Windows must also select a compatible loop before starting;
the default Proactor loop is unsupported by Psycopg async connections.
Windows Selector loops have Python's socket-count and asynchronous
subprocess/pipe limitations; this is local development support, not evidence
of Windows production capacity. Linux container startup is unchanged.

From `frontend`, set the three public `VITE_` inputs and run:

```text
npm run dev
```

Vite prints its loopback URL and proxies `/api` to port 8000. Register that
exact development origin as a SPA redirect in the existing Entra application.
Interactive sign-in requires valid existing Entra configuration; the
synthetic application does not require a model. Do not expose the reload
server publicly or put credentials in Vite configuration.

The project includes VS Code tasks and launch configurations in `.vscode/`.
Open the project root, select `backend/.venv`, and use the backend or Chrome
launch configurations as described in the [README](../README.md). Interactive
debugger operation is unverified. Be careful not to inspect or record tokens,
payloads, or secrets. Check startup failures and recovery messages in the
local process or Compose service logs. See [operations](operations.md).

The tests use isolated identities, not an interactive login bypass. Use the
[test guide](testing.md) to validate extensions, including recovery.
