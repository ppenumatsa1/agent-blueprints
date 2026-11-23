import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from order_resolution_hosted.application import CallerContext
from order_resolution_hosted.host import (
    _INSTRUMENTATION_OPTIONS,
    _PRIVACY_ENVIRONMENT,
    _caller,
    _configure_host_observability,
    _conversation,
    _start_case,
    parse_turn,
    run,
)


class FakeApplication:
    def __init__(self):
        self.started = []
        self.resumed = []

    def authorize_start(self, caller, conversation_id, case_id):
        self.started.append((caller, conversation_id, case_id))
        return {"case_id": str(case_id)}

    def authorize_resume(self, caller, conversation_id, request_id, value):
        self.resumed.append((caller, conversation_id, request_id, value))
        return value


class FakeRequest:
    def __init__(self, *, items, text=None, responses=None):
        self.scope = SimpleNamespace(user_id="user", session_id="session", call_id="call")
        self.conversation_id = "conversation"
        self._items = items
        self._text = text
        self._responses = responses
        self.workflow_responses_called = False

    async def get_input_items(self):
        return self._items

    async def get_input_text(self):
        return self._text

    async def get_workflow_responses(self):
        self.workflow_responses_called = True
        return self._responses


class ProtocolTests(unittest.TestCase):
    def test_runtime_defers_maf_construction_until_after_agentserver_setup(self):
        server = SimpleNamespace(run=lambda: None)
        with (
            patch(
                "order_resolution_hosted.host.ResponsesHostServer",
                return_value=server,
            ) as responses_host,
            patch("order_resolution_hosted.host.load_application") as load,
        ):
            run()
            responses_host.assert_called_once()
            load.assert_not_called()

            workflow = responses_host.call_args.kwargs["workflow"]
            application = SimpleNamespace(
                build_workflow=lambda caller, conversation: (caller, conversation)
            )
            load.return_value = application
            request = SimpleNamespace(
                scope=SimpleNamespace(
                    user_id="user",
                    session_id="session",
                    call_id="call",
                ),
                conversation_id="conversation",
            )
            caller, conversation = workflow(request)
        self.assertEqual(caller.user_id, "user")
        self.assertEqual(conversation, "conversation")
        load.assert_called_once_with()

    def test_host_observability_uses_supported_builtins_with_privacy_disabled(self):
        order = []
        with (
            patch(
                "order_resolution_hosted.host.enable_instrumentation",
                side_effect=lambda **_: order.append("enable"),
            ) as enable,
            patch(
                "order_resolution_hosted.host.configure_agentserver_observability",
                side_effect=lambda **_: order.append("configure"),
            ) as configure,
        ):
            _configure_host_observability(
                connection_string="InstrumentationKey=test",
                log_level="INFO",
                enable_sensitive_data=True,
            )
        enable.assert_called_once_with(
            enable_sensitive_data=False,
            enable_message_events=False,
            force=True,
        )
        configure.assert_called_once_with(
            connection_string="InstrumentationKey=test",
            log_level="INFO",
            enable_sensitive_data=False,
            instrumentation_options=_INSTRUMENTATION_OPTIONS,
        )
        self.assertEqual(order, ["configure", "enable"])
        self.assertEqual(
            _PRIVACY_ENVIRONMENT,
            {
                "ENABLE_SENSITIVE_DATA": "false",
                "ENABLE_MESSAGE_EVENTS": "false",
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
            },
        )

    def test_requires_trusted_caller_and_conversation_binding(self):
        request = SimpleNamespace(
            scope=SimpleNamespace(user_id="user", session_id="session", call_id="call"),
            conversation_id="conversation",
        )
        self.assertEqual(_caller(request), CallerContext("user", "session", "call"))
        self.assertEqual(_conversation(request), "conversation")
        for field in ("user_id", "session_id", "call_id"):
            with self.subTest(field=field):
                broken = SimpleNamespace(
                    scope=SimpleNamespace(user_id="user", session_id="session", call_id="call"),
                    conversation_id="conversation",
                )
                setattr(broken.scope, field, None)
                with self.assertRaises(PermissionError):
                    _caller(broken)
        request.conversation_id = None
        with self.assertRaises(PermissionError):
            _conversation(request)

    def test_start_command_is_exact_and_structured(self):
        case_id = uuid4()
        self.assertEqual(_start_case(json.dumps({"case_id": str(case_id)})), case_id)
        for value in (
            None,
            str(case_id),
            "{}",
            json.dumps({"case_id": str(case_id), "extra": True}),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _start_case(value)

    def test_parser_uses_native_checkpoint_validation_before_resume(self):
        application = FakeApplication()
        value = {"decision": "approved"}
        request = FakeRequest(
            items=[
                SimpleNamespace(
                    type="function_call_output",
                    call_id="request-1",
                    output=json.dumps(value),
                )
            ],
            responses={"request-1": value},
        )
        turn = asyncio.run(parse_turn(application, request))
        self.assertTrue(request.workflow_responses_called)
        self.assertEqual(turn.responses, {"request-1": value})
        self.assertEqual(application.resumed[0][2], "request-1")

    def test_parser_rejects_non_workflow_approval_response(self):
        request = FakeRequest(
            items=[{"type": "mcp_approval_response"}],
            responses={},
        )
        with self.assertRaises(PermissionError):
            asyncio.run(parse_turn(FakeApplication(), request))


if __name__ == "__main__":
    unittest.main()
