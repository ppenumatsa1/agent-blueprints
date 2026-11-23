import unittest
from pathlib import Path
from uuid import UUID

from app.api.routes.acceptance import _authorized
from app.config import Settings
from app.domain.errors import AccessDenied
from app.domain.models import Principal
from app.infrastructure.identity import AuthenticatedRequest
from app.order_resolution.acceptance import AcceptanceFaults
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.service import OrderResolutionService


CASE_ID = UUID("10000000-0000-4000-8000-000000000001")
REVISION = "a" * 40


class AcceptanceFaultTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
