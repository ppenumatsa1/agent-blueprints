import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from unittest.mock import patch

from app.domain.models import Case
from app.order_resolution.durability import (
    Decision,
    DecisionCommand,
    DecisionRecord,
    Proposal,
)
from order_resolution_hosted.application import CallerContext
from order_resolution_hosted.business import (
    AmbiguousBusinessOperation,
    ApiTokenProvider,
    HttpHostedBusinessStore,
)


class Credential:
    def __init__(self):
        self.scopes = []

    def get_token(self, scope):
        self.scopes.append(scope)
        return SimpleNamespace(token="hosted-mi-token")


class Response:
    def __init__(self, status_code, body=None, *, malformed=False):
        self.status_code = status_code
        self._body = body
        self._malformed = malformed

    def json(self):
        if self._malformed:
            raise ValueError("malformed")
        return self._body

    def raise_for_status(self):
        request = httpx.Request("POST", "https://api.example.test/internal")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("request failed", request=request, response=response)


class BusinessStoreTests(unittest.TestCase):
    def setUp(self):
        self.case_id = uuid4()
        self.case = Case(
            id=self.case_id,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload={"proposal": {"approval_required": True}},
            status="created",
            decision=None,
            request_id=None,
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=False,
            failure_code=None,
        )
        self.proposal = Proposal(
            case_id=str(self.case_id),
            proposal_version=1,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            input_digest="a" * 64,
            policy_evidence_digest="b" * 64,
            policy_version="POLICY-LATE@1",
            action="partial_refund_10",
            destination_id="synthetic-refund",
            approval_required=True,
            reason_codes=("manual_review",),
            decision_handle_digest="c" * 64,
            decision_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
            decision_channel="foundry-responses",
        )
        self.decision = DecisionRecord(
            case_id=str(self.case_id),
            proposal_version=1,
            action="partial_refund_10",
            destination_id="synthetic-refund",
            decision=Decision.APPROVED,
            actor_id="reviewer",
            tenant_id="tenant",
            scope="workflow.approve",
            channel="foundry-responses",
            decided_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.caller = CallerContext("hosted-user", "hosted-session", "hosted-call")
        self.credential = Credential()
        self.calls = []

    @staticmethod
    def serialized(value):
        body = asdict(value)
        for key, item in tuple(body.items()):
            if isinstance(item, datetime):
                body[key] = item.isoformat()
            elif isinstance(item, tuple):
                body[key] = list(item)
            elif hasattr(item, "value"):
                body[key] = item.value
            elif hasattr(item, "hex"):
                body[key] = str(item)
        return body

    def serialized_case(self):
        body = self.serialized(self.case)
        del body["checkpoint_id"]
        del body["terminal_checkpoint_id"]
        return body

    def response(self, _method, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/bindings/start"):
            return Response(
                200,
                {
                    "tenant_id": "tenant",
                    "subject": "owner",
                    "scopes": ["workflow.read"],
                    "roles": [],
                },
            )
        if url.endswith("/bindings/resume"):
            return Response(
                200,
                {
                    "tenant_id": "tenant",
                    "subject": "reviewer",
                    "scopes": ["workflow.read", "workflow.approve"],
                    "roles": ["Workflow.Approver"],
                },
            )
        if url.endswith("/proposal/read") or url.endswith("/approvals/prepare"):
            return Response(200, self.serialized(self.proposal))
        if url.endswith("/decisions/claim"):
            return Response(200, self.serialized(self.decision))
        if url.endswith("/read") or url.endswith("/effects/apply") or url.endswith("/finish"):
            return Response(200, self.serialized_case())
        raise AssertionError(url)

    def store(self, request=None):
        return HttpHostedBusinessStore(
            "https://api.example.test/internal/order-resolution/hosted",
            ApiTokenProvider("api://order-resolution-api/.default", self.credential),
            request=request or self.response,
        )

    def test_prewarm_uses_only_the_configured_internal_api_scope(self):
        store = self.store()
        store.prewarm()
        self.assertEqual(self.credential.scopes, ["api://order-resolution-api/.default"])
        self.assertEqual(self.calls, [])

    def test_write_submission_span_is_stable_and_payload_free(self):
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        try:
            bound = self.store().for_binding(self.caller, "conversation", "owner")
            with patch(
                "app.order_resolution.observability.trace.get_tracer",
                return_value=provider.get_tracer("test"),
            ):
                bound.prepare_hosted_approval(
                    self.case_id,
                    "approval-request",
                    channel="foundry-responses",
                )
            span = exporter.get_finished_spans()[-1]
            self.assertEqual(span.name, "workflow.resolution_submit")
            self.assertEqual(span.attributes["blueprint.workflow.status"], "succeeded")
            self.assertNotIn("approval-request", span.to_json())
        finally:
            provider.shutdown()

    def test_https_wire_uses_managed_identity_and_bound_flat_contract(self):
        store = self.store()
        owner = store.resolve_start_principal(
            case_id=self.case_id,
            caller=self.caller,
            conversation_id="conversation",
        )
        bound_owner = store.for_binding(self.caller, "conversation", "owner")
        case = bound_owner.get(self.case_id)
        proposal = bound_owner.prepare_hosted_approval(
            self.case_id,
            "approval-request",
            channel="foundry-responses",
        )
        current = bound_owner.get_current_proposal(str(self.case_id))

        reviewer = store.authorize_resume(
            case_id=self.case_id,
            caller=self.caller,
            conversation_id="conversation",
            channel="foundry-responses",
        )
        bound_reviewer = store.for_binding(self.caller, "conversation", "reviewer")
        decision = bound_reviewer.record_hosted_decision(
            DecisionCommand(
                case_id=str(self.case_id),
                proposal_version=1,
                action="partial_refund_10",
                destination_id="synthetic-refund",
                handle="approval-request",
                decision=Decision.APPROVED,
                scope="workflow.approve",
                channel="foundry-responses",
            )
        )
        bound_reviewer.apply_once(self.case_id, True, object())
        bound_reviewer.finish_hosted(self.case_id)

        self.assertEqual(owner.subject, "owner")
        self.assertEqual(reviewer.subject, "reviewer")
        self.assertEqual(case.id, self.case_id)
        self.assertIsNone(case.checkpoint_id)
        self.assertEqual(proposal, current)
        self.assertEqual(decision, self.decision)
        self.assertEqual(
            self.credential.scopes,
            ["api://order-resolution-api/.default"] * len(self.calls),
        )
        writes = [kwargs for _, kwargs in self.calls if kwargs["headers"].get("Idempotency-Key")]
        self.assertEqual(len(writes), 6)
        self.assertTrue(
            all(
                kwargs["headers"]["Authorization"] == "Bearer hosted-mi-token"
                for _, kwargs in self.calls
            )
        )
        self.assertTrue(all(url.startswith("https://api.example.test/") for url, _ in self.calls))
        payloads = [kwargs["json"] for _, kwargs in self.calls]
        self.assertTrue(all("caller" not in payload for payload in payloads))
        self.assertTrue(all(payload["platform_user_id"] == "hosted-user" for payload in payloads))
        self.assertTrue(
            all(payload["platform_session_id"] == "hosted-session" for payload in payloads)
        )
        self.assertTrue(all(payload["platform_call_id"] == "hosted-call" for payload in payloads))
        read_payloads = [
            kwargs["json"]
            for url, kwargs in self.calls
            if url.endswith("/read") or url.endswith("/proposal/read")
        ]
        self.assertEqual(
            [payload["principal_kind"] for payload in read_payloads],
            ["owner", "owner"],
        )

    def test_missing_preestablished_binding_fails_without_follow_on_business_calls(self):
        calls = []

        def missing(*args, **kwargs):
            calls.append((args, kwargs))
            return Response(404, {"detail": "binding not found"})

        store = self.store(missing)
        with self.assertRaises(httpx.HTTPStatusError):
            store.resolve_start_principal(
                case_id=self.case_id,
                caller=self.caller,
                conversation_id="conversation",
            )
        with self.assertRaises(httpx.HTTPStatusError):
            store.authorize_resume(
                case_id=self.case_id,
                caller=self.caller,
                conversation_id="conversation",
                channel="foundry-responses",
            )
        self.assertEqual(len(calls), 2)

    def test_wrong_preestablished_binding_fails_closed(self):
        calls = []

        def mismatch(*args, **kwargs):
            calls.append((args, kwargs))
            payload = kwargs["json"]
            if payload["conversation_id"] != "conversation":
                return Response(403, {"detail": "binding mismatch"})
            raise AssertionError("The test must use a mismatched binding.")

        store = self.store(mismatch)
        with self.assertRaises(httpx.HTTPStatusError):
            store.resolve_start_principal(
                case_id=self.case_id,
                caller=CallerContext("wrong-user", "wrong-session", "wrong-call"),
                conversation_id="wrong-conversation",
            )
        self.assertEqual(len(calls), 1)

    def test_lost_write_acknowledgment_is_not_replayed(self):
        calls = []

        def timeout(*args, **kwargs):
            calls.append((args, kwargs))
            raise TimeoutError("lost")

        bound = self.store(timeout).for_binding(self.caller, "conversation", "reviewer")
        for _ in range(2):
            with self.assertRaises(AmbiguousBusinessOperation):
                bound.apply_once(self.case_id, True, object())
        self.assertEqual(len(calls), 1)

    def test_malformed_success_is_unknown_and_not_replayed(self):
        calls = []

        def malformed(*args, **kwargs):
            calls.append((args, kwargs))
            return Response(200, malformed=True)

        bound = self.store(malformed).for_binding(self.caller, "conversation", "owner")
        for _ in range(2):
            with self.assertRaises(AmbiguousBusinessOperation):
                bound.apply_automatic(self.case_id, object())
        self.assertEqual(len(calls), 1)

    def test_authorization_failure_is_explicit_and_loopback_matching_is_exact(self):
        calls = []

        def forbidden(*args, **kwargs):
            calls.append((args, kwargs))
            return Response(403, {"detail": "forbidden"})

        bound = self.store(forbidden).for_binding(self.caller, "conversation", "owner")
        with self.assertRaises(httpx.HTTPStatusError):
            bound.get(self.case_id)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            HttpHostedBusinessStore(
                "http://localhost.example/internal",
                ApiTokenProvider("api://order-resolution-api/.default", self.credential),
            )


if __name__ == "__main__":
    unittest.main()
