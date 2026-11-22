import asyncio
import json
import unittest
from types import SimpleNamespace
from uuid import uuid4

from order_resolution_hosted.application import CallerContext
from order_resolution_hosted.host import _caller, _conversation, _start_case, parse_turn


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
