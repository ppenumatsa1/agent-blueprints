import asyncio
from hashlib import sha256
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent_framework import Agent, FunctionTool, Workflow

from app.domain.errors import AccessDenied
from app.domain.models import Principal
from app.extensions.agents import AgentDefinition, build_chat_agent
from app.extensions.model import ModelSelection, select_chat_client
from app.extensions.prompts import load_prompt_asset
from app.extensions.tools import ToolRegistry
from app.workflows.workflow import create_workflow
from examples.synthetic_application import (
    PROMPT_PATH,
    SYNTHETIC_AGENT,
    SyntheticToolAuthorization,
    _inspect_synthetic_case,
    build_application,
    build_synthetic_agent,
    build_synthetic_tools,
)


class UnavailableChatClient:
    @property
    def additional_properties(self):
        return {}

    async def get_response(self, messages, **kwargs):
        raise RuntimeError("No model provider is configured for this test.")

    def get_streaming_response(self, messages, **kwargs):
        raise RuntimeError("No model provider is configured for this test.")


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.client = UnavailableChatClient()
        self.reader = Principal("tenant", "reader", frozenset({"workflow.read"}), frozenset())
        self.denied = Principal("tenant", "denied", frozenset(), frozenset())

    def test_model_selection_requires_explicit_valid_configuration_and_provider(self):
        for provider_id, model_id in (("", "model"), ("provider", ""), ("provider ", "model")):
            with self.subTest(provider_id=provider_id, model_id=model_id):
                with self.assertRaises(ValueError):
                    ModelSelection(provider_id, model_id)

        selection = ModelSelection("synthetic-provider", "synthetic-model")
        factory = Mock(return_value=self.client)
        self.assertIs(select_chat_client(selection, {"synthetic-provider": factory}), self.client)
        factory.assert_called_once_with(selection)
        with self.assertRaisesRegex(ValueError, "No model provider"):
            select_chat_client(selection, {})

    def test_model_provider_must_return_a_maf_chat_client(self):
        selection = ModelSelection("provider", "model")
        with self.assertRaisesRegex(TypeError, "MAF chat client"):
            select_chat_client(selection, {"provider": lambda _: object()})

    def test_prompt_assets_require_explicit_version_and_matching_file(self):
        prompt = load_prompt_asset("synthetic-review", "v1", PROMPT_PATH)
        self.assertEqual(prompt.version, "v1")
        self.assertEqual(prompt.content_sha256, sha256(PROMPT_PATH.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prompt.txt"
            path.write_text("Synthetic instructions.", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicit vN"):
                load_prompt_asset("prompt", "latest", path)
            with self.assertRaisesRegex(ValueError, "path must match"):
                load_prompt_asset("prompt", "v1", path)

    def test_agent_composition_uses_native_maf_agent_without_running_a_model(self):
        prompt = load_prompt_asset("synthetic-review", "v1", PROMPT_PATH)
        definition = AgentDefinition(
            SYNTHETIC_AGENT.name,
            SYNTHETIC_AGENT.description,
            SYNTHETIC_AGENT.prompt_name,
            SYNTHETIC_AGENT.prompt_version,
        )
        agent = build_chat_agent(definition, self.client, prompt)
        self.assertIsInstance(agent, Agent)
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_chat_agent(
                AgentDefinition("agent", "description", "prompt", "v2"),
                self.client,
                prompt,
            )

        provider = Mock(return_value=self.client)
        synthetic_agent = build_synthetic_agent(
            ModelSelection("synthetic-provider", "synthetic-model"),
            {"synthetic-provider": provider},
            self.reader,
            SyntheticToolAuthorization(),
        )
        self.assertIsInstance(synthetic_agent, Agent)
        provider.assert_called_once_with(ModelSelection("synthetic-provider", "synthetic-model"))

    def test_tool_authorization_is_checked_before_the_tool_result(self):
        authorization = SyntheticToolAuthorization()
        denied_tool = build_synthetic_tools(self.denied, authorization)[0]
        self.assertIsInstance(denied_tool, FunctionTool)
        with self.assertRaises(AccessDenied):
            asyncio.run(
                denied_tool.invoke(arguments={"case_id": "untrusted-model-supplied-case-id"})
            )
        reader_tool = build_synthetic_tools(self.reader, authorization)[0]
        with self.assertRaises(AccessDenied):
            asyncio.run(reader_tool.invoke(arguments={"case_id": "unauthorized-case-id"}))
        result = asyncio.run(reader_tool.invoke(arguments={"case_id": "synthetic-case"}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "Synthetic case reference: synthetic-case")

    def test_tool_authorization_requires_affirmative_true_before_reading(self):
        for result in (False, None, 1):
            with self.subTest(result=result):
                authorization = Mock()
                authorization.authorize_tool.return_value = result
                with patch(
                    "examples.synthetic_application._read_synthetic_case_reference"
                ) as read_case:
                    with self.assertRaises(AccessDenied):
                        asyncio.run(
                            _inspect_synthetic_case(self.reader, authorization, "synthetic-case")
                        )
                    read_case.assert_not_called()

    def test_tool_registry_rejects_duplicate_names_and_binds_request_principal(self):
        registry = ToolRegistry()
        factory = Mock(return_value=FunctionTool(name="synthetic_tool"))
        registry.register("synthetic_tool", factory)
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register("synthetic_tool", factory)
        authorization = SyntheticToolAuthorization()
        registry.bind(self.reader, authorization)
        factory.assert_called_once_with(self.reader, authorization)

    def test_workflow_extension_remains_a_native_maf_workflow(self):
        application = build_application()
        self.assertIsNot(application.workflow_factory, create_workflow)
        workflow = application.workflow_factory(Mock(), Mock(), None)
        self.assertIsInstance(workflow, Workflow)


if __name__ == "__main__":
    unittest.main()
