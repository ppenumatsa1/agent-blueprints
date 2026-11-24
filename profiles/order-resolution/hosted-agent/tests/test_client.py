import threading
import unittest
from types import SimpleNamespace

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from opentelemetry.trace import StatusCode
from unittest.mock import patch

from order_resolution_hosted.client import (
    AmbiguousCreate,
    ConversationBinding,
    HostedResponseFailed,
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


class MalformedResponse(FakeResponse):
    def json(self):
        raise ValueError("private-response-body")


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.journal = MemoryOperationJournal()
        self.credential = FakeCredential()
        self.binding = ConversationBinding("conversation")

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
        payload = requests[0][1]["json"]
        self.assertTrue(payload["background"])
        self.assertNotIn("agent_session_id", payload)
        self.assertEqual(payload["metadata"], {"operation_id": "start-1"})

    def test_prewarm_populates_only_the_foundry_scope_without_sending_a_request(self):
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        class TracedCredential(FakeCredential):
            def get_token(self, scope):
                with tracer.start_as_current_span("GET /msi/token", kind=SpanKind.CLIENT):
                    return super().get_token(scope)

        requests = []
        credential = TracedCredential()
        client = ResponsesClient(
            "https://example.test/agents/order/endpoint/responses?api-version=v1",
            self.journal,
            token_provider=TokenProvider(credential),
            post=lambda *args, **kwargs: requests.append((args, kwargs)),
        )
        try:
            with patch(
                "order_resolution_hosted.credentials.trace.get_tracer",
                return_value=tracer,
            ):
                client.prewarm()
            spans = {span.name: span for span in exporter.get_finished_spans()}
            boundary = spans["application.credentials.prewarm"]
            token = spans["GET /msi/token"]
            self.assertEqual(credential.scopes, ["https://ai.azure.com/.default"])
            self.assertEqual(requests, [])
            self.assertEqual(token.parent.span_id, boundary.context.span_id)
            self.assertEqual(
                boundary.attributes["blueprint.credential.owner"],
                "application",
            )
            self.assertEqual(
                boundary.attributes["blueprint.credential.audience"],
                "foundry",
            )
        finally:
            provider.shutdown()

    def test_prewarm_failure_is_visible_without_exception_content(self):
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        class FailingCredential:
            @staticmethod
            def get_token(_scope):
                raise RuntimeError("private credential detail")

        client = ResponsesClient(
            "https://example.test/agents/order/endpoint/responses?api-version=v1",
            self.journal,
            token_provider=TokenProvider(FailingCredential()),
            post=lambda *_args, **_kwargs: None,
        )
        try:
            with (
                patch(
                    "order_resolution_hosted.credentials.trace.get_tracer",
                    return_value=provider.get_tracer("test"),
                ),
                self.assertRaisesRegex(RuntimeError, "private credential detail"),
            ):
                client.prewarm()
            span = exporter.get_finished_spans()[-1]
            self.assertEqual(span.name, "application.credentials.prewarm")
            self.assertEqual(span.status.status_code, StatusCode.ERROR)
            self.assertEqual(span.attributes["error.type"], "RuntimeError")
            self.assertFalse(span.events)
            self.assertNotIn("private credential detail", span.to_json())
        finally:
            provider.shutdown()

    def test_current_w3c_context_is_injected_without_sensitive_headers(self):
        requests = []
        provider = TracerProvider()
        tracer = provider.get_tracer("test")

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return FakeResponse()

        with tracer.start_as_current_span("api.foundry", kind=SpanKind.CLIENT) as span:
            expected_trace_id = f"{span.get_span_context().trace_id:032x}"
            self.client(post).start(
                operation_id="start-traced",
                binding=self.binding,
                case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
            )
        headers = requests[0][1]["headers"]
        self.assertRegex(
            headers["traceparent"],
            rf"^00-{expected_trace_id}-[0-9a-f]{{16}}-[0-9a-f]{{2}}$",
        )
        self.assertNotIn("baggage", {name.casefold() for name in headers})
        self.assertNotIn("tracestate", {name.casefold() for name in headers})

    def test_conversation_create_returns_bound_identity(self):
        requests = []

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return FakeResponse(body={"id": "conversation-created"})

        binding = self.client(post).create_conversation(
            operation_id="conversation-1",
        )
        self.assertEqual(
            binding,
            ConversationBinding("conversation-created"),
        )
        self.assertIn("/conversations", requests[0][0][0])
        self.assertEqual(
            requests[0][1]["json"],
            {"metadata": {"operation_id": "conversation-1"}},
        )

    def test_rejects_insecure_conversation_endpoint(self):
        for endpoint in (
            "http://example.test/conversations",
            "http://localhost.example/conversations",
            "https://user:password@example.test/conversations",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    ResponsesClient(
                        "https://example.test/responses",
                        self.journal,
                        conversation_endpoint=endpoint,
                        token_provider=TokenProvider(self.credential),
                    )

    def test_accepts_exact_loopback_http_endpoint(self):
        for endpoint in (
            "http://localhost:8080/responses",
            "http://127.0.0.1:8080/responses",
            "http://[::1]:8080/responses",
        ):
            with self.subTest(endpoint=endpoint):
                ResponsesClient(
                    endpoint,
                    self.journal,
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

    def test_token_failure_does_not_claim_and_later_retry_posts_once(self):
        requests = []

        class FlakyTokenProvider:
            def __init__(self):
                self.calls = 0

            def authorization_header(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("token unavailable")
                return "Bearer recovered-token"

        token_provider = FlakyTokenProvider()

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return FakeResponse()

        client = ResponsesClient(
            "https://example.test/agents/order/endpoint/responses?api-version=v1",
            self.journal,
            token_provider=token_provider,
            post=post,
        )

        with self.assertRaisesRegex(RuntimeError, "token unavailable"):
            client.start(
                operation_id="start-token-retry",
                binding=self.binding,
                case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
            )
        self.assertIsNone(self.journal.get("start-token-retry"))
        self.assertEqual(requests, [])

        for _ in range(2):
            self.assertEqual(
                client.start(
                    operation_id="start-token-retry",
                    binding=self.binding,
                    case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
                ),
                "resp-1",
            )
        self.assertEqual(token_provider.calls, 2)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            self.journal.get("start-token-retry").status,
            OperationStatus.ACKNOWLEDGED,
        )

    def test_existing_pending_claim_is_unknown_and_never_sent(self):
        case_id = "c3dc94c3-7772-4249-bf63-95597591f49c"
        client = self.client(lambda *_args, **_kwargs: self.fail("POST must not run"))
        payload = {
            "background": True,
            "conversation": {"id": self.binding.conversation_id},
            "input": '{"case_id":"' + case_id + '"}',
            "metadata": {"operation_id": "start-pending"},
            "store": True,
        }
        claim = self.journal.claim(
            "start-pending",
            client._digest(client._endpoint, payload),
        )
        self.assertTrue(claim.acquired)
        with self.assertRaises(AmbiguousCreate):
            client.start(
                operation_id="start-pending",
                binding=self.binding,
                case_id=case_id,
            )
        self.assertEqual(
            self.journal.get("start-pending").status,
            OperationStatus.UNKNOWN,
        )

    def test_concurrent_pending_claim_does_not_duplicate_post(self):
        entered = threading.Event()
        release = threading.Event()
        calls = 0

        def post(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            entered.set()
            release.wait(timeout=5)
            return FakeResponse()

        client = self.client(post)
        errors = []

        def first():
            try:
                client.start(
                    operation_id="start-concurrent",
                    binding=self.binding,
                    case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
                )
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=first)
        thread.start()
        self.assertTrue(entered.wait(timeout=5))
        with self.assertRaises(AmbiguousCreate):
            client.start(
                operation_id="start-concurrent",
                binding=self.binding,
                case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
            )
        release.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(calls, 1)
        self.assertEqual(
            self.journal.get("start-concurrent").status,
            OperationStatus.ACKNOWLEDGED,
        )

    def test_malformed_success_is_unknown_without_private_response_evidence(self):
        client = self.client(lambda *_args, **_kwargs: MalformedResponse())
        with self.assertRaises(AmbiguousCreate) as captured:
            client.start(
                operation_id="start-malformed",
                binding=self.binding,
                case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
            )
        self.assertNotIn("private-response-body", str(captured.exception))
        self.assertIsNone(captured.exception.__cause__)
        self.assertIsNone(captured.exception.__context__)
        self.assertEqual(
            self.journal.get("start-malformed").status,
            OperationStatus.UNKNOWN,
        )
        with self.assertRaises(AmbiguousCreate):
            client.start(
                operation_id="start-malformed",
                binding=self.binding,
                case_id="c3dc94c3-7772-4249-bf63-95597591f49c",
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

    def test_explicit_response_failure_is_terminal_and_retains_remote_id(self):
        requests = []

        def post(*args, **kwargs):
            requests.append((args, kwargs))
            return FakeResponse(
                body={"id": "resp-failed", "status": "failed", "error": {"message": "private"}}
            )

        arguments = {
            "operation_id": "start-failed",
            "binding": self.binding,
            "case_id": "c3dc94c3-7772-4249-bf63-95597591f49c",
        }
        client = self.client(post)
        with self.assertRaises(HostedResponseFailed) as captured:
            client.start(**arguments)
        self.assertNotIn("private", str(captured.exception))
        record = self.journal.get("start-failed")
        self.assertEqual((record.status, record.remote_id), (OperationStatus.FAILED, "resp-failed"))
        self.assertEqual(client.reconcile_acknowledgment("start-failed", ["resp-failed"]), record)
        with self.assertRaises(HostedResponseFailed):
            self.client(post).start(**arguments)
        with self.assertRaisesRegex(ValueError, "different request content"):
            client.start(**{**arguments, "case_id": "different-case"})
        self.assertEqual(len(requests), 1)

    def test_resume_rejects_cross_channel_or_conversation(self):
        client = self.client(lambda *_args, **_kwargs: FakeResponse())
        decision = {
            "handle": "request-1",
            "channel": "api",
            "conversation_id": "conversation",
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
        self.assertNotIn("agent_session_id", requests[0][1]["json"])


if __name__ == "__main__":
    unittest.main()
