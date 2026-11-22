import unittest
from types import SimpleNamespace

from order_resolution_hosted.client import (
    AmbiguousCreate,
    ConversationBinding,
    MemoryOperationJournal,
    OperationStatus,
    ResponsesClient,
    TokenProvider,
)


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, scope):
        self.scopes.append(scope)
        return SimpleNamespace(token="managed-identity-token")


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {"id": "resp-1"}

    def json(self):
        return self._body

    def raise_for_status(self):
        raise RuntimeError(f"HTTP {self.status_code}")


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.journal = MemoryOperationJournal()
        self.credential = FakeCredential()
        self.binding = ConversationBinding("caller", "conversation", "session")

    def client(self, post):
        return ResponsesClient(
            "https://example.test/agents/order/endpoint/responses?api-version=v1",
            self.journal,
            conversation_endpoint="https://example.test/openai/conversations?api-version=v1",
            token_provider=TokenProvider(self.credential),
            post=post,
        )

    def test_managed_identity_token_and_duplicate_acknowledgment(self):
        requests = []

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return FakeResponse()

        client = self.client(post)
        first = client.start(
            operation_id="start-1",
            binding=self.binding,
            case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
        )
        duplicate = client.start(
            operation_id="start-1",
            binding=self.binding,
            case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
        )
        self.assertEqual((first, duplicate), ("resp-1", "resp-1"))
        self.assertEqual(len(requests), 1)
        self.assertEqual(self.credential.scopes, ["https://ai.azure.com/.default"])
        self.assertEqual(
            requests[0][1]["headers"]["Authorization"],
            "Bearer managed-identity-token",
        )
        self.assertTrue(requests[0][1]["json"]["background"])

    def test_conversation_create_returns_bound_identity(self):
        requests = []

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return FakeResponse(body={"id": "conversation-created"})

        binding = self.client(post).create_conversation(
            operation_id="conversation-1",
            caller_id="caller",
            session_id="session",
        )
        self.assertEqual(
            binding,
            ConversationBinding("caller", "conversation-created", "session"),
        )
        self.assertIn("/conversations", requests[0][0][0])

    def test_rejects_insecure_conversation_endpoint(self):
        with self.assertRaises(ValueError):
            ResponsesClient(
                "https://example.test/responses",
                self.journal,
                conversation_endpoint="http://example.test/conversations",
                token_provider=TokenProvider(self.credential),
            )

    def test_lost_acknowledgment_is_unknown_and_never_replayed(self):
        calls = 0

        def post(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise TimeoutError("ack lost")

        client = self.client(post)
        for _ in range(2):
            with self.assertRaises(AmbiguousCreate):
                client.start(
                    operation_id="start-unknown",
                    binding=self.binding,
                    case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
                )
        self.assertEqual(calls, 1)
        self.assertEqual(
            self.journal.get("start-unknown").status,
            OperationStatus.UNKNOWN,
        )

    def test_authoritative_reconciliation_requires_one_remote_id(self):
        client = self.client(lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
        with self.assertRaises(AmbiguousCreate):
            client.start(
                operation_id="start-reconcile",
                binding=self.binding,
                case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
            )
        unchanged = client.reconcile_acknowledgment("start-reconcile", [])
        self.assertEqual(unchanged.status, OperationStatus.UNKNOWN)
        reconciled = client.reconcile_acknowledgment(
            "start-reconcile",
            ["resp-authoritative"],
        )
        self.assertEqual(reconciled.status, OperationStatus.ACKNOWLEDGED)
        self.assertEqual(reconciled.remote_id, "resp-authoritative")

    def test_resume_rejects_cross_channel_or_conversation(self):
        client = self.client(lambda *_args, **_kwargs: FakeResponse())
        decision = {
            "handle": "request-1",
            "channel": "api",
            "conversation_id": "conversation",
            "session_id": "session",
        }
        with self.assertRaises(PermissionError):
            client.resume(
                operation_id="resume-1",
                binding=self.binding,
                request_id="request-1",
                decision=decision,
            )

    def test_resume_serializes_structured_function_output(self):
        requests = []

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return FakeResponse()

        decision = {
            "handle": "request-1",
            "channel": "foundry-responses",
            "conversation_id": "conversation",
            "session_id": "session",
            "decision": "approved",
        }
        self.client(post).resume(
            operation_id="resume-structured",
            binding=self.binding,
            request_id="request-1",
            decision=decision,
        )
        output = requests[0][1]["json"]["input"][0]["output"]
        self.assertIsInstance(output, str)
        self.assertEqual(__import__("json").loads(output), decision)


if __name__ == "__main__":
    unittest.main()
