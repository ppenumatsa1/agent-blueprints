# Agent Blueprints

Agent Blueprints is the agent implementation family of the proposed Software
Factory. It will provide framework-specific reference architectures for
independently buildable customer projects, not a shared production runtime or
another coding-agent platform.

**Current state: Phase 1 in progress.** A local readiness validator, synthetic
acceptance fixtures, and the local [MAF workflow blueprint](blueprints/maf/workflow/)
are available. The authenticated application has local automated coverage and
a Compose smoke check; independent generated-project verification, live
Entra sign-in, and hosted compatibility remain unverified. No Azure resources
are deployed.

The first planned golden path is a Microsoft Agent Framework (MAF) workflow:
Foundry Hosted Agents are the preferred public-network hosting path, subject to
verification; Azure Container Apps is the fallback. Public endpoints must
still be authenticated and authorized.

## Start here

- [Software Factory overview](docs/software-factory-overview.md)
- [Interactive architecture: original source](docs/software-factory.html)
- [Living master checklist](docs/master-checklist.md)
- [Agent Blueprints architecture and proposed structure](docs/agent-blueprints-architecture.md)
- [Reference repository analysis](docs/reference-repository-analysis.md)
- [Blueprint catalog and hosting compatibility](docs/blueprint-catalog.md)
- [Engineering standards](docs/engineering-standards.md)
- [Readiness contract](docs/readiness-contract.md)
- [Local readiness validator](docs/readiness-validator.md)
- [Synthetic order-adjustment fixture](scenarios/order-adjustment/README.md)
- [Phased implementation plan](docs/implementation-plan.md)
- [Copilot development conventions](.github/copilot-instructions.md)

The supplied HTML is a historical design source; the overview, plan, and
checklist track current decisions and progress.

The [contracts](contracts/) directory contains versioned, proposed JSON Schemas.
Their synthetic examples are test fixtures, **not evidence of an actual release
or customer approval**. Schema validation checks document shape; it does not
authenticate reviewers, verify an evidence artifact, or replace a release gate.
The local validator checks signed decisions and evidence, but its trust store
and result producers require independent administration. The included scenario
is unapproved, and its application acceptance adapter is not yet implemented.

## Validate the contracts

With Python 3.12 or later, create and activate a
[virtual environment](https://docs.python.org/3/library/venv.html), then run:

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

OpenSSL is also required for the validator tests. GitHub Actions runs the same
checks on GitHub-hosted runners without Azure credentials. The application
acceptance test remains unverified until the blueprint adapter exists; a skipped
test is not evidence that an application passed. Do not commit customer data,
credentials, tenant-specific configuration, or private evidence.

## License and reference projects

This repository is licensed under the [MIT License](LICENSE).

**Caution:** The [MAF monorepo](https://github.com/ppenumatsa1/maf-monorepo),
[LangGraph workflows](https://github.com/ppenumatsa1/langgraph-wf-monorepo), and
[Model to Harness](https://github.com/ppenumatsa1/model-to-harness) are
separate reference projects. Consult each project's documentation and license
before reuse, and independently verify its security and suitability; examples or
historical deployments are not production assurances.
