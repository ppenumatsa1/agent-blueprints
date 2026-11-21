# Project structure

```text
README.md              project entry point
docs/                  guides and design records
backend/app/           API, use cases, domain, native workflow, adapters
backend/examples/      explicitly selected synthetic application
backend/tests/         security, durability, evidence and extension tests
frontend/              React client, build and UI tests
compose.yaml           local prototype services
verification/          copied verifier, contracts and synthetic fixture*
```

`*` The verification directory exists in an independently generated project,
not the source blueprint alone. A generated project owns its files and must
not import or mount the source repository at runtime.

The current backend image copies `app` and `examples`. Application-owned
modules added elsewhere require an intentional Dockerfile change. See
[extension recipes](../architecture.md), [setup](../setup.md) and
[testing](../testing.md).
