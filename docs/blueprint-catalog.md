# Blueprint catalog and compatibility

The local MAF workflow blueprint is in progress; the other entries are
planned. A documented platform integration is not a verified blueprint
deployment, and no entry is represented as ready for customer use.

| Priority | Blueprint | Framework / execution | Initial direction |
| --- | --- | --- | --- |
| P0 | MAF Workflow | Microsoft Agent Framework / explicit workflow | First golden path |
| P1 | MAF Harness | Microsoft Agent Framework / harness | After Phase 1 |
| P1 | Foundry Project SDK Agent | Foundry SDK / single agent | Choose prompt-agent versus application-owned definition in Phase 2 |
| P1 | LangGraph Workflow | LangGraph / stateful graph | Phase 3 |
| P2 | Deep Agents | Deep Agents / harness | Phase 4 |
| P2 | Copilot SDK Harness | GitHub Copilot SDK / harness | Phase 5 |

## Hosting matrix

`Verified` requires a reproducible result for the specified blueprint,
revision, configuration, and environment. `Unsupported` requires an
authoritative source for the specific combination. `Requires validation`
includes documented platform support that has not been tested for our
blueprint. `N/A` means the combination is not the selected architecture.

| Blueprint | Local development | Foundry Hosted Agent | Azure Container Apps | Foundry prompt agent |
| --- | --- | --- | --- | --- |
| MAF Workflow | Compose smoke checked; independent project and live identity require validation | Requires validation; native Python workflow hosting is documented | Requires validation; fallback | N/A: prompt agents do not host the custom workflow |
| MAF Harness | Requires validation | Requires validation | Requires validation | N/A |
| Foundry Project SDK Agent | Requires validation | Requires validation if custom container selected | Requires validation if application-owned | Requires validation; prompt-agent runtime is documented |
| LangGraph Workflow | Requires validation | Requires validation; LangGraph hosting is documented | Requires validation | N/A |
| Deep Agents | Requires validation | Requires validation; hosting through the LangGraph adapter is documented | Requires validation | N/A |
| Copilot SDK Harness | Requires validation | Requires validation; a reference reports a historical deployment | Requires validation | N/A; SDK harness is not the Foundry prompt-agent harness |

No combination is marked unsupported merely because it has not been tried.
Foundry prompt agents are declarative managed agents; Foundry Hosted Agents run
custom code. A Foundry prompt agent's optional managed Copilot harness is not
the same product boundary as embedding the GitHub Copilot SDK.

## Sources and constraints

- [MAF Foundry hosting](https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent):
  native Python workflows, request-aware factories, and host-managed
  checkpoints; Python hosting integration is prerelease.
- [LangGraph and Deep Agents hosting](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-hosted-agents):
  documented Responses/Invocations adapter paths.
- [Foundry prompt agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/prompt-agents):
  managed prompt runtime versus hosted custom code.
- [Copilot SDK documentation](https://github.com/microsoft/copilot-sdk/tree/main/docs):
  runtime, authentication, provider, and deployment choices require their own
  compatibility review.
- [Reference analysis](reference-repository-analysis.md): implementation and
  historical evidence, with pinned revisions and limitations.

For each future verified entry, record package/runtime versions, protocol,
identity, state storage, network mode, test or deployment run, and revision.
Private-network compatibility is deliberately deferred.
