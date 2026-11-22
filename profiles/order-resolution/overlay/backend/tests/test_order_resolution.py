import unittest
from uuid import uuid4

from app.domain.models import Case
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.workflow import build_order_resolution_workflow


def payload(
    *,
    order_id: str = "ORDER-LOW",
    amount: str = "79.00",
    issue: str = "late_delivery",
    delay_days: int | None = 4,
    policy_id: str = "POLICY-LATE@1",
) -> dict:
    order = {"id": order_id, "amount": amount, "currency": "USD", "issue": issue}
    if delay_days is not None:
        order["delay_days"] = delay_days
    return {
        "order": order,
        "policy_evidence": [
            {
                "policy": policy_id,
                "current": True,
                "applicable": True,
                "digest_valid": True,
            }
        ],
    }


class FakeStore:
    def __init__(self, case):
        self.case = case
        self.automatic = 0

    def get(self, _case_id):
        return self.case

    def apply_automatic(self, _case_id, _action):
        self.automatic += 1

    def apply_once(self, _case_id, _approved, _action):
        raise AssertionError("A decision should not be applied in this test.")


class OrderResolutionRulesTests(unittest.TestCase):
    def setUp(self):
        self.rules = OrderResolutionRules()

    def test_low_and_high_refunds_are_deterministic(self):
        low = self.rules.validate(payload())
        high = self.rules.validate(payload(order_id="ORDER-HIGH", amount="185.00", delay_days=5))
        self.assertEqual(
            (
                low["proposal"]["action"],
                low["proposal"]["amount"],
                low["proposal"]["approval_required"],
            ),
            ("partial_refund_10", "7.90", False),
        )
        self.assertEqual(
            (
                high["proposal"]["action"],
                high["proposal"]["amount"],
                high["proposal"]["approval_required"],
            ),
            ("partial_refund_10", "18.50", True),
        )

    def test_damaged_item_proposes_one_approval_gated_replacement(self):
        result = self.rules.validate(
            payload(
                order_id="ORDER-DAMAGED",
                issue="damaged_item",
                delay_days=None,
                policy_id="POLICY-DAMAGED@1",
            )
        )
        self.assertEqual(result["proposal"]["action"], "replacement_shipment")
        self.assertTrue(result["proposal"]["approval_required"])
        self.assertNotIn("amount", result["proposal"])

    def test_missing_conflicting_and_invalid_evidence_fail_explicitly(self):
        cases = []
        missing = payload()
        missing["policy_evidence"] = []
        cases.append((missing, "policy_evidence_missing"))
        conflict = payload()
        conflict["policy_evidence"].append(dict(conflict["policy_evidence"][0]))
        cases.append((conflict, "policy_evidence_conflict"))
        invalid = payload()
        invalid["policy_evidence"][0]["digest_valid"] = False
        cases.append((invalid, "policy_evidence_invalid"))
        for value, code in cases:
            with self.subTest(code=code):
                result = self.rules.validate(value)
                self.assertEqual(result["resolution_failure"], code)
                self.assertIsNone(result["proposal"])


class OrderResolutionWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_workflow_auto_completes_low_risk_proposal(self):
        normalized = OrderResolutionRules().validate(payload())
        case_id = uuid4()
        case = Case(
            id=case_id,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload=normalized,
            status="created",
            decision=None,
            request_id=None,
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=False,
            failure_code=None,
        )
        store = FakeStore(case)
        workflow = build_order_resolution_workflow(store, object())
        outputs = []
        async for event in workflow.run({"case_id": str(case_id)}, stream=True):
            if event.type == "output":
                outputs.append(event.data)
        self.assertEqual(outputs, [{"case_id": str(case_id), "decision": "automatic"}])
        self.assertEqual(store.automatic, 1)


if __name__ == "__main__":
    unittest.main()
