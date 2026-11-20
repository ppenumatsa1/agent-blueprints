# Agent Blueprints

Agent Blueprints is the agent implementation family of the proposed Software
Factory. It will provide framework-specific reference architectures for
independently buildable customer projects, not a shared production runtime or
another coding-agent platform.

**Current state: Phase 0 foundation.** The architecture, readiness rules,
initial contracts, and implementation plan are proposals. There are no runnable
agent templates or deployed Azure resources in this repository yet.

The first planned golden path is a Microsoft Agent Framework (MAF) workflow:
Foundry Hosted Agents are the preferred public-network hosting path, subject to
verification; Azure Container Apps is the fallback. Public endpoints must
still be authenticated and authorized.

## Start here

- [Software Factory overview](docs/software-factory-overview.md)
- [Agent Blueprints architecture and proposed structure](docs/agent-blueprints-architecture.md)
- [Reference repository analysis](docs/reference-repository-analysis.md)
- [Blueprint catalog and hosting compatibility](docs/blueprint-catalog.md)
- [Engineering standards](docs/engineering-standards.md)
- [Readiness contract](docs/readiness-contract.md)
- [Phased implementation plan](docs/implementation-plan.md)
- [Copilot development conventions](.github/copilot-instructions.md)

The [contracts](contracts/) directory contains versioned, proposed JSON Schemas.
Their synthetic examples are test fixtures, **not evidence of an actual release
or customer approval**. Schema validation checks document shape; it does not
authenticate reviewers, verify an evidence artifact, or replace a release gate.

## Validate the contracts

With Python 3.12 or later, create and activate a
[virtual environment](https://docs.python.org/3/library/venv.html), then run:

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

GitHub Actions runs the same checks on GitHub-hosted runners without Azure
credentials. Do not commit customer data, credentials, tenant-specific
configuration, or private evidence to this public repository.
