import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.domain.models import Principal
from app.order_resolution.durability import Decision, DecisionCommand
from order_resolution_hosted.bridge import (
    HOSTED_CHANNEL,
    ResponsesWorkflowHost,
    build_workflow_host,
)
from order_resolution_hosted.client import (
    FOUNDRY_SCOPE,
    ConversationBinding,
    MemoryOperationJournal,
    ResponsesClient,
    TokenProvider,
)


class FakeResponses:
    def __init__(self, events):
        self.events = events

    def create_conversation(self, **values):
        self.events.append(("conversation", values))
        return ConversationBinding("conversation-server-selected")

    def start(self, **values):
        self.events.append(("start", values))
        return "response-start"

    def resume(self, **values):
        self.events.append(("resume", values))
        return "response-resume"


class FakeAuthority:
    def __init__(self, events, binding=None):
        self.events = events
        self.binding = binding

    def bind_start(self, case_id, principal, **values):
        self.events.append(("bind-start", case_id, principal, values))
        self.binding = ConversationBinding(values["conversation_id"])

    def load_binding(self, case_id):
        self.events.append(("load-binding", case_id))
        return self.binding

    def bind_resume(self, case_id, principal, **values):
        self.events.append(("bind-resume", case_id, principal, values))


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def test_initialize_prewarms_the_app_owned_foundry_credential(self):
        responses = Mock()
        host = ResponsesWorkflowHost(responses, Mock())
        host.initialize()
        responses.prewarm.assert_called_once_with()

    def setUp(self):
        self.case_id = uuid4()
        self.owner = Principal(
            "tenant",
            "owner",
            frozenset({"workflow.read"}),
            frozenset(),
        )
        self.reviewer = Principal(
            "tenant",
            "reviewer",
            frozenset({"workflow.read", "workflow.approve"}),
            frozenset({"Workflow.Approver"}),
        )

    def command(self, **changes):
        values = {
            "case_id": str(self.case_id),
            "proposal_version": 2,
            "action": "partial_refund_10",
            "destination_id": "synthetic-refund",
            "handle": "approval-request",
            "decision": Decision.APPROVED,
            "scope": "workflow.approve",
            "channel": HOSTED_CHANNEL,
        }
        values.update(changes)
        return DecisionCommand(**values)

    async def test_start_creates_conversation_then_prebinds_before_responses_dispatch(self):
        events = []
        authority = FakeAuthority(events)
        host = ResponsesWorkflowHost(FakeResponses(events), authority)

        await host.start(self.case_id, self.owner)

        self.assertEqual([event[0] for event in events], ["conversation", "bind-start", "start"])
        conversation = events[0][1]
        self.assertEqual(conversation["operation_id"], f"case:{self.case_id}:conversation")
        self.assertNotIn("caller_id", conversation)
        self.assertNotIn("session_id", conversation)
        binding = events[1][3]
        self.assertEqual(binding["conversation_id"], "conversation-server-selected")
        self.assertNotIn("caller_id", binding)
        self.assertNotIn("session_id", binding)
        self.assertEqual(events[2][1]["operation_id"], f"case:{self.case_id}:start")
        self.assertNotIn("agent_session_id", events[2][1])

    async def test_resume_loads_and_prebinds_reviewer_intent_before_function_output(self):
        events = []
        authority = FakeAuthority(
            events,
            ConversationBinding("conversation-server-selected"),
        )
        host = ResponsesWorkflowHost(FakeResponses(events), authority)
        command = self.command()

        await host.resume(self.case_id, self.reviewer, command)

        self.assertEqual(
            [event[0] for event in events],
            ["load-binding", "bind-resume", "resume"],
        )
        resume_binding = events[1][3]
        self.assertEqual(resume_binding["conversation_id"], "conversation-server-selected")
        self.assertNotIn("caller_id", resume_binding)
        self.assertNotIn("session_id", resume_binding)
        self.assertIs(resume_binding["decision_command"], command)
        request = events[2][1]
        self.assertEqual(
            request["operation_id"],
            f"case:{self.case_id}:decision:2",
        )
        self.assertEqual(request["request_id"], "approval-request")
        self.assertEqual(
            request["decision"]["conversation_id"],
            "conversation-server-selected",
        )
        self.assertNotIn("session_id", request["decision"])
        self.assertNotIn("agent_session_id", request)

    async def test_terminal_resume_uses_acknowledged_journal_without_redispatch(self):
        requests = []

        class Credential:
            @staticmethod
            def get_token(scope):
                return SimpleNamespace(token="token")

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"id": "response-terminal"}

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return Response()

        authority = FakeAuthority(
            [],
            ConversationBinding("conversation-server-selected"),
        )
        responses = ResponsesClient(
            "https://project.services.ai.azure.com/responses?api-version=v1",
            MemoryOperationJournal(),
            token_provider=TokenProvider(Credential()),
            post=post,
        )
        host = ResponsesWorkflowHost(responses, authority)
        command = self.command()

        await host.resume(self.case_id, self.reviewer, command)
        await host.resume(self.case_id, self.reviewer, command)

        self.assertEqual(len(requests), 1)

        with self.assertRaises(ValueError):
            await host.resume(
                self.case_id,
                self.reviewer,
                self.command(action="different-valid-action"),
            )
        self.assertEqual(len(requests), 1)

    async def test_invalid_decision_never_prebinds_or_dispatches(self):
        events = []
        authority = FakeAuthority(
            events,
            ConversationBinding("conversation"),
        )
        host = ResponsesWorkflowHost(FakeResponses(events), authority)

        with self.assertRaises(PermissionError):
            await host.resume(
                self.case_id,
                self.reviewer,
                self.command(scope="different.scope"),
            )

        self.assertEqual([event[0] for event in events], ["load-binding"])

    def test_factory_uses_explicit_foundry_endpoints_scope_and_api_identity(self):
        settings = SimpleNamespace(
            hosted_workflow_endpoint="https://project.services.ai.azure.com/responses?api-version=v1",
            hosted_conversation_endpoint=(
                "https://project.services.ai.azure.com/conversations?api-version=v1"
            ),
            hosted_workflow_scope=FOUNDRY_SCOPE,
            api_managed_identity_client_id="api-uami-client-id",
        )
        responses = object()
        with (
            patch("order_resolution_hosted.bridge.ManagedIdentityCredential") as credential_type,
            patch(
                "order_resolution_hosted.bridge.ResponsesClient", return_value=responses
            ) as client,
        ):
            host = build_workflow_host(
                settings,
                object(),
                FakeAuthority([]),
                MemoryOperationJournal(),
            )

        credential_type.assert_called_once_with(client_id="api-uami-client-id")
        self.assertIs(host._responses, responses)
        self.assertEqual(client.call_args.args[0], settings.hosted_workflow_endpoint)
        self.assertEqual(
            client.call_args.kwargs["conversation_endpoint"],
            settings.hosted_conversation_endpoint,
        )

    def test_factory_fails_closed_without_supported_scope_or_store(self):
        settings = SimpleNamespace(
            hosted_workflow_endpoint="https://project.test/responses?api-version=v1",
            hosted_conversation_endpoint="https://project.test/conversations?api-version=v1",
            hosted_workflow_scope="api://wrong/.default",
            api_managed_identity_client_id="client-id",
        )
        with self.assertRaises(ValueError):
            build_workflow_host(
                settings,
                object(),
                FakeAuthority([]),
                MemoryOperationJournal(),
            )
        settings.hosted_workflow_scope = FOUNDRY_SCOPE
        with self.assertRaises(TypeError):
            build_workflow_host(
                settings,
                None,
                FakeAuthority([]),
                MemoryOperationJournal(),
            )


if __name__ == "__main__":
    unittest.main()
