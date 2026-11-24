import io
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from app.api.routes.acceptance import _authorized, case_control
from app.config import Settings
from app.domain.errors import AccessDenied, NotFound
from app.domain.models import Case, Principal
from app.infrastructure.identity import AuthenticatedRequest
from app.order_resolution.acceptance import AcceptanceFaults
from app.order_resolution.durability import Proposal
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.service import OrderResolutionService
from tests.live_acceptance import LiveClient


CASE_ID = UUID("10000000-0000-4000-8000-000000000001")
REVISION = "a" * 40


class FakeResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class FakeConnection:
    def __init__(self):
        self.results = [
            {
                "approved": 0,
                "rejected": 0,
                "claims": 1,
                "effects": 1,
                "terminal": 1,
                "denials": 0,
            },
            [{"action": "partial_refund_10", "amount": "7.90", "currency": "USD"}],
        ]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args):
        return FakeResult(self.results.pop(0))


class AcceptanceFaultTests(unittest.TestCase):
    def test_live_client_uses_response_correlation_id_for_telemetry_pair(self):
        case_id = "20000000-0000-4000-8000-000000000002"
        request_id = "30000000-0000-4000-8000-000000000003"
        trace_id = "4" * 32

        class Response:
            status = 200
            headers = {
                "X-Correlation-ID": request_id,
                "traceparent": f"00-{trace_id}-{'5' * 16}-01",
            }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def read():
                return f'{{"id":"{case_id}"}}'.encode()

        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.deployment_revision = REVISION
        client.correlations = []
        with (
            patch("tests.live_acceptance.urllib.request.urlopen", return_value=Response()),
            patch.dict("os.environ", {"AGENT_VERSION": "1"}),
        ):
            status, _, _ = client.request(
                "POST",
                "/api/cases",
                {"access_token": "token"},
                body={"synthetic": True},
            )

        self.assertEqual(status, 200)
        self.assertEqual(
            client.correlations,
            [
                {
                    "request_id": request_id,
                    "case_id": case_id,
                    "trace_id": trace_id,
                    "agent_version": "1",
                    "deployment_revision": REVISION,
                    "http_status": 200,
                }
            ],
        )
        self.assertIs(type(client.correlations[0]["http_status"]), int)

    def test_live_client_records_http_status_for_denied_requests(self):
        case_id = "20000000-0000-4000-8000-000000000002"
        request_id = "30000000-0000-4000-8000-000000000003"
        trace_id = "4" * 32

        headers = {
            "X-Correlation-ID": request_id,
            "traceparent": f"00-{trace_id}-{'5' * 16}-01",
        }

        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.deployment_revision = REVISION
        client.correlations = []
        with (
            patch(
                "tests.live_acceptance.urllib.request.urlopen",
                side_effect=urllib.error.HTTPError(
                    "https://api.example.test/api/cases",
                    403,
                    "Forbidden",
                    headers,
                    io.BytesIO(f'{{"id":"{case_id}"}}'.encode()),
                ),
            ),
            patch.dict("os.environ", {"AGENT_VERSION": "1"}),
        ):
            status, _, _ = client.request(
                "POST",
                "/api/cases",
                {"access_token": "token"},
                body={"synthetic": True},
            )

        self.assertEqual(status, 403)
        self.assertEqual(client.correlations[0]["http_status"], 403)
        self.assertIs(type(client.correlations[0]["http_status"]), int)

    def test_controls_are_revision_bound_and_one_shot(self):
        faults = AcceptanceFaults(enabled=True, deployment_revision=REVISION)
        faults.authorize_revision(REVISION)
        with self.assertRaises(PermissionError):
            faults.authorize_revision("b" * 40)

        faults.set_ack_fault(CASE_ID, "decision-ack-lost", True)
        self.assertEqual(faults.armed(CASE_ID), ["decision-ack-lost"])
        self.assertTrue(faults.consume_ack_fault(CASE_ID, "claim-decision"))
        self.assertFalse(faults.consume_ack_fault(CASE_ID, "claim-decision"))
        self.assertEqual(faults.observed(CASE_ID), ["decision-ack-lost"])

    def test_disabled_controls_fail_closed(self):
        faults = AcceptanceFaults(enabled=False, deployment_revision=REVISION)
        with self.assertRaises(PermissionError):
            faults.authorize_revision(REVISION)

    def test_acceptance_mode_requires_hosted_runtime(self):
        with self.assertRaisesRegex(ValueError, "only in hosted mode"):
            Settings(
                tenant_id="11111111-1111-4111-8111-111111111111",
                api_client_id="22222222-2222-4222-8222-222222222222",
                database_url="postgresql://test",
                checkpoint_root=Path("checkpoints"),
                host_mode="local",
                acceptance_mode=True,
            )

    def test_route_authorization_requires_role_and_exact_revision(self):
        store = object.__new__(OrderResolutionStore)
        store.acceptance_faults = AcceptanceFaults(
            enabled=True,
            deployment_revision=REVISION,
        )
        service = object.__new__(OrderResolutionService)
        service.store = store

        operator = AuthenticatedRequest(
            Principal(
                "tenant",
                "operator",
                frozenset({"workflow.write"}),
                frozenset({"Acceptance.Operator"}),
            ),
            "token",
        )
        self.assertEqual(_authorized(operator, service, REVISION), (store, store.acceptance_faults))

        unauthorized = AuthenticatedRequest(
            Principal("tenant", "user", frozenset({"workflow.write"}), frozenset()),
            "token",
        )
        with self.assertRaises(AccessDenied):
            _authorized(unauthorized, service, REVISION)
        with self.assertRaises(AccessDenied):
            _authorized(operator, service, "b" * 40)

    def test_snapshot_uses_case_payload_for_proposal_money(self):
        store = object.__new__(OrderResolutionStore)
        store.get = lambda _case_id: Case(
            id=CASE_ID,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload={
                "proposal": {
                    "amount": "7.90",
                    "currency": "USD",
                }
            },
            status="completed",
            decision=None,
            request_id=None,
            checkpoint_id=None,
            terminal_checkpoint_id="terminal",
            execution_complete=True,
            failure_code=None,
        )
        store.get_current_proposal = lambda _case_id: Proposal(
            case_id=str(CASE_ID),
            proposal_version=1,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            input_digest="1" * 64,
            policy_evidence_digest="2" * 64,
            policy_version="POLICY-LATE@1",
            action="partial_refund_10",
            destination_id="synthetic-refund",
            approval_required=False,
            reason_codes=("late_delivery",),
            decision_handle_digest=None,
            decision_expires_at=None,
            decision_channel=None,
        )
        store.connect = FakeConnection

        snapshot = store.acceptance_snapshot(CASE_ID)

        self.assertEqual(snapshot["proposal"]["amount"], "7.90")
        self.assertEqual(snapshot["proposal"]["currency"], "USD")
        self.assertEqual(snapshot["counts"]["effects"], 1)

    def test_case_control_supports_fail_closed_cases_without_hosted_binding(self):
        store = object.__new__(OrderResolutionStore)
        store.acceptance_faults = AcceptanceFaults(
            enabled=True,
            deployment_revision=REVISION,
        )

        def missing_binding(_case_id):
            raise NotFound("The hosted platform binding is not available.")

        store.acceptance_binding = missing_binding
        store.acceptance_snapshot = lambda _case_id: {
            "status": "failed",
            "counts": {"effects": 0},
        }
        service = object.__new__(OrderResolutionService)
        service.store = store
        operator = AuthenticatedRequest(
            Principal(
                "tenant",
                "operator",
                frozenset({"workflow.read"}),
                frozenset({"Acceptance.Operator"}),
            ),
            "token",
        )

        result = case_control(CASE_ID, REVISION, operator, service)

        self.assertIsNone(result["conversation_id"])
        self.assertIsNone(result["platform_session_id"])
        self.assertEqual(result["snapshot"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
