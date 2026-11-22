# Development and debugging

Complete [setup](setup.md) first. Compose is the simplest integrated path;
only the web port is published. For a direct local run, use a separately
accessible PostgreSQL database, a private checkpoint directory, and set all
direct backend inputs in the launching environment. From `backend`, with the
virtual environment active:

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

From `frontend`, set the three public `VITE_` inputs and run:

```text
npm run dev
```

Vite prints its loopback URL and proxies `/api` to port 8000. Register that
exact development origin as a SPA redirect in the existing Entra application.
Interactive sign-in requires valid existing Entra configuration; the
synthetic application does not require a model. Do not expose the reload
server publicly or put credentials in Vite configuration.

For debugging, set breakpoints in the backend or frontend and launch the
commands above from your editor's integrated terminal; attach an appropriate
local debugger to the running process or browser using the editor's own
instructions. No checked-in VS Code launch/tasks configuration or debugger
attachment service is provided. Be careful not to inspect or record tokens,
payloads, or secrets. Check startup failures and recovery messages in the
local process or Compose service logs. See [operations](operations.md).

The tests use isolated identities, not an interactive login bypass. Use the
[test guide](testing.md) to validate extensions, including recovery. uv, Ruff,
and richer debugger presets are planned rather than current commands.
