import inspect
import os
import unittest
from importlib.metadata import version
from unittest.mock import patch

from agent_framework.observability import enable_instrumentation
from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    FoundryRequestScope,
    HostedResponseRequest,
    ResponsesHostServer,
    WorkflowTurn,
)
from azure.ai.agentserver.core import (
    AgentConfig,
    AgentServerHost,
    FoundryAgentRequestContext,
    configure_observability,
)
from azure.ai.projects.models import (
    CodeConfiguration,
    HostedAgentDefinition,
    ProtocolVersionRecord,
)
from azure.ai.projects.operations import AgentsOperations
from order_resolution_hosted.model import create_chat_client


class SdkCompatibilityTests(unittest.TestCase):
    def test_exact_supported_versions_are_installed(self):
        expected = {
            "agent-framework-core": "1.26.0",
            "agent-framework-foundry": "1.16.2",
            "agent-framework-foundry-hosting": "1.0.0b261112",
            "azure-ai-agentserver-core": "2.3.1b1",
            "azure-ai-agentserver-responses": "2.4.0",
            "azure-ai-projects": "2.11.0",
            "azure-identity": "1.27.0",
            "azure-monitor-opentelemetry-exporter": "1.0.0b59",
            "httpx": "0.28.1",
            "opentelemetry-api": "1.45.2",
            "opentelemetry-sdk": "1.45.2",
        }
        self.assertEqual({name: version(name) for name in expected}, expected)

    def test_public_hosting_and_publishing_surface_has_not_drifted(self):
        host = inspect.signature(ResponsesHostServer)
        for parameter in (
            "workflow",
            "parse_response",
            "checkpoint_store_provider",
            "options",
        ):
            self.assertIn(parameter, host.parameters)
        self.assertIn("kwargs", host.parameters)
        agent_server_host = inspect.signature(AgentServerHost)
        for parameter in (
            "applicationinsights_connection_string",
            "configure_observability",
        ):
            self.assertIn(parameter, agent_server_host.parameters)
        for parameter in (
            "connection_string",
            "enable_sensitive_data",
            "instrumentation_options",
        ):
            self.assertIn(parameter, inspect.signature(configure_observability).parameters)
        for parameter in (
            "enable_sensitive_data",
            "enable_message_events",
            "force",
        ):
            self.assertIn(parameter, inspect.signature(enable_instrumentation).parameters)
        for member in ("get_input_items", "get_input_text", "get_workflow_responses"):
            self.assertTrue(inspect.iscoroutinefunction(getattr(HostedResponseRequest, member)))
        self.assertIn("responses", inspect.signature(WorkflowTurn).parameters)
        self.assertIn(
            "allowed_checkpoint_types", inspect.signature(CheckpointStoreProvider).parameters
        )

        publish = inspect.signature(AgentsOperations.create_version_from_code)
        for parameter in (
            "agent_name",
            "definition",
            "code",
            "code_zip_sha256",
            "metadata",
        ):
            self.assertIn(parameter, publish.parameters)
        definition = HostedAgentDefinition(
            cpu="0.5",
            memory="1Gi",
            code_configuration=CodeConfiguration(
                runtime="python_3_13",
                entry_point=["python", "main.py"],
                dependency_resolution="remote_build",
            ),
            protocol_versions=[ProtocolVersionRecord(protocol="responses", version="2.0.0")],
        )
        self.assertEqual(definition.code_configuration.runtime, "python_3_13")
        self.assertEqual(definition.protocol_versions[0].version, "2.0.0")

    def test_platform_scope_rejects_conflicting_caller_session(self):
        config = AgentConfig(
            agent_name="order-resolution",
            agent_version="1",
            agent_id="agent-id",
            is_hosted=True,
            project_endpoint="https://project.example.test",
            project_id="project-id",
            session_id="platform-session",
            port=8088,
            appinsights_connection_string="",
            otlp_endpoint="",
            sse_keepalive_interval=15,
        )
        context = FoundryAgentRequestContext(
            call_id="platform-call",
            user_id="api-workload-user",
            session_id="platform-session",
        )
        scope = FoundryRequestScope.from_context(config, context)
        self.assertEqual(scope.session_id, "platform-session")
        self.assertEqual(scope.user_id, "api-workload-user")
        self.assertEqual(scope.call_id, "platform-call")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            FoundryRequestScope.from_context(
                config,
                FoundryAgentRequestContext(
                    call_id="platform-call",
                    user_id="api-workload-user",
                    session_id="caller-invented-session",
                ),
            )

    def test_foundry_chat_client_uses_only_injected_endpoint_and_model(self):
        credential = object()
        client = object()
        with (
            patch.dict(
                os.environ,
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://project.example.test",
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "configured-deployment",
                },
                clear=True,
            ),
            patch(
                "order_resolution_hosted.model.DefaultAzureCredential",
                return_value=credential,
            ),
            patch(
                "order_resolution_hosted.model.FoundryChatClient",
                return_value=client,
            ) as chat,
        ):
            self.assertIs(create_chat_client(), client)
        chat.assert_called_once_with(
            project_endpoint="https://project.example.test",
            model="configured-deployment",
            credential=credential,
        )


if __name__ == "__main__":
    unittest.main()
