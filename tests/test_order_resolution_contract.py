"""Validate the versioned Order Resolution acceptance contract and optional adapter."""

import json
import os
import subprocess
import sys
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "order-resolution"
CONTRACT = json.loads((SCENARIO / "acceptance-contract.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((SCENARIO / "golden-cases.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in GOLDEN["cases"]}


def assert_subset(test_case, expected, actual, path="actual"):
    if isinstance(expected, dict):
        test_case.assertIsInstance(actual, dict, path)
        for key, value in expected.items():
            test_case.assertIn(key, actual, path)
            assert_subset(test_case, value, actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        test_case.assertEqual(len(actual), len(expected), path)
        for index, value in enumerate(expected):
            assert_subset(test_case, value, actual[index], f"{path}[{index}]")
        return
    test_case.assertEqual(actual, expected, path)


class OrderResolutionContractTests(unittest.TestCase):
    def test_contract_identity_and_exact_case_set(self):
        self.assertEqual(CONTRACT["contract_id"], "order-resolution-spec")
        self.assertEqual(CONTRACT["contract_version"], "0.1.0")
        self.assertEqual(CONTRACT["scenario_set"], "order-resolution-spec/0.1.0")
        self.assertEqual(GOLDEN["scenario_set"], CONTRACT["scenario_set"])
        self.assertEqual(
            list(CASES),
            [f"ORS-{number:03d}" for number in range(1, 10)],
        )

    def test_exact_synthetic_facts_and_policies(self):
        self.assertEqual(
            CONTRACT["orders"],
            {
                "ORDER-LOW": {
                    "amount": "79.00",
                    "issue": "late_delivery",
                    "delay_days": 4,
                    "owner": "USER-A",
                },
                "ORDER-HIGH": {
                    "amount": "185.00",
                    "issue": "late_delivery",
                    "delay_days": 5,
                    "owner": "USER-A",
                },
                "ORDER-DAMAGED": {
                    "amount": "79.00",
                    "issue": "damaged_item",
                    "owner": "USER-A",
                },
            },
        )
        late = CONTRACT["policies"]["POLICY-LATE@1"]
        self.assertEqual(late["applicability"], {"issue": "late_delivery", "delay_days_greater_than": 3})
        self.assertEqual(late["proposed_action"], {"type": "partial_refund_10"})
        self.assertEqual(
            late["approval_required_when"],
            {"order_amount_usd_greater_than_or_equal": "100.00"},
        )
        self.assertEqual(
            CONTRACT["policies"]["POLICY-DAMAGED@1"],
            {
                "applicability": {"issue": "damaged_item"},
                "proposed_action": {"type": "replacement_shipment", "quantity": 1},
                "approval_required": True,
            },
        )
        self.assertEqual(
            CONTRACT["idempotency"]["action_claim_key"],
            ["case_id", "proposal_version", "action"],
        )
        self.assertEqual(CONTRACT["idempotency"]["maximum_claims_per_key"], 1)
        self.assertEqual(
            CONTRACT["reviewer_authorization"],
            {
                "REVIEWER-A": {"may_decide_owner_cases": ["USER-A"]},
                "USER-B": {"may_decide_owner_cases": []},
                "REVIEWER-B": {"may_decide_owner_cases": []},
            },
        )
        self.assertEqual(
            CONTRACT["policy_evidence"],
            {
                "authoritative_requirement": {
                    "cardinality": 1,
                    "current": True,
                    "applicable": True,
                    "digest_valid": True,
                },
                "failure_outcomes": {
                    "missing": "policy_evidence_missing",
                    "conflicting": "policy_evidence_conflict",
                    "invalid": "policy_evidence_invalid",
                },
            },
        )

    def test_partial_refund_decimal_rounding_and_expected_amounts(self):
        rule = CONTRACT["amounts"]["partial_refund_10"]
        self.assertEqual(CONTRACT["amounts"]["currency"], "USD")
        self.assertEqual(CONTRACT["amounts"]["representation"], "decimal_string")
        self.assertEqual(rule["rate"], "0.10")
        self.assertEqual(rule["rounding"], "ROUND_HALF_UP")
        self.assertEqual(rule["round_once_to_decimal_places"], 2)

        for order_id, case_ids, expected_amount in (
            ("ORDER-LOW", ("ORS-001", "ORS-004"), "7.90"),
            ("ORDER-HIGH", ("ORS-002", "ORS-005", "ORS-009"), "18.50"),
        ):
            calculated = (
                Decimal(CONTRACT["orders"][order_id]["amount"]) * Decimal(rule["rate"])
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.assertEqual(format(calculated, ".2f"), expected_amount)
            for case_id in case_ids:
                self.assertEqual(
                    CASES[case_id]["expected"]["business_outcome"]["proposed_action"]["amount"],
                    expected_amount,
                )

    def test_business_and_technical_assertions_are_separate(self):
        business_only = {
            "proposal_authoritative",
            "proposed_action",
            "approval_required",
            "decision",
            "verified_actions",
            "state",
            "error",
            "returned_original_outcome",
        }
        technical_only = {
            "native_pause_required",
            "native_pause_before_action",
            "authorized_decision_count",
            "rejection_count",
            "action_claim_count",
            "side_effect_count",
            "terminal_event_count",
            "request_identity_reused",
            "duplicate_terminal_event_emitted",
            "termination_point",
            "native_continuation_reconciled",
            "stored_decision_reused",
            "original_decision_audit_preserved",
            "invalid_variants_checked",
            "all_variants_failed_explicitly",
            "terminal_event_count_per_variant",
            "denied_actors",
            "authorization_denial_count",
            "denial_privacy_safe",
            "denial_auditable",
        }
        for case in CASES.values():
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    set(case["expected"]),
                    {"business_outcome", "technical_execution"},
                )
                business = set(case["expected"]["business_outcome"])
                technical = set(case["expected"]["technical_execution"])
                self.assertTrue(business <= business_only)
                self.assertTrue(technical <= technical_only)
                self.assertFalse(business & technical)

    def test_exact_business_outcome_matrix(self):
        expected = {
            "ORS-001": ("partial_refund_10", "7.90", False, "not_required", "completed", 1, None),
            "ORS-002": ("partial_refund_10", "18.50", True, "approved", "completed", 1, None),
            "ORS-003": ("replacement_shipment", None, True, "rejected", "escalated", 0, None),
            "ORS-004": ("partial_refund_10", "7.90", False, "not_required", "completed", 1, None),
            "ORS-005": ("partial_refund_10", "18.50", True, "approved", "completed", 1, None),
            "ORS-006": (None, None, None, "none", "failed", 0, "policy_evidence_missing"),
            "ORS-007": (None, None, None, "none", "failed", 0, "policy_evidence_conflict"),
            "ORS-008": (None, None, None, "none", "failed", 0, "policy_evidence_invalid"),
            "ORS-009": (
                "partial_refund_10",
                "18.50",
                True,
                "pending",
                "awaiting_approval",
                0,
                "authorization_denied",
            ),
        }
        for case_id, (
            action_type,
            amount,
            approval_required,
            decision,
            state,
            verified_action_count,
            error,
        ) in expected.items():
            with self.subTest(case=case_id):
                business = CASES[case_id]["expected"]["business_outcome"]
                action = business["proposed_action"]
                self.assertEqual(action["type"] if action else None, action_type)
                self.assertEqual(action.get("amount") if action else None, amount)
                self.assertEqual(business["approval_required"], approval_required)
                self.assertEqual(business["decision"], decision)
                self.assertEqual(business["state"], state)
                self.assertEqual(len(business["verified_actions"]), verified_action_count)
                self.assertEqual(business.get("error"), error)

    def test_approval_action_and_recovery_expectations(self):
        self.assertFalse(CASES["ORS-001"]["expected"]["business_outcome"]["approval_required"])
        self.assertTrue(CASES["ORS-002"]["expected"]["technical_execution"]["native_pause_before_action"])
        self.assertEqual(
            CASES["ORS-002"]["expected"]["technical_execution"]["authorized_decision_count"],
            1,
        )

        damaged = CASES["ORS-003"]["expected"]
        self.assertEqual(
            damaged["business_outcome"]["proposed_action"],
            {"type": "replacement_shipment", "quantity": 1},
        )
        self.assertEqual(damaged["business_outcome"]["decision"], "rejected")
        self.assertEqual(damaged["business_outcome"]["state"], "escalated")
        self.assertEqual(damaged["technical_execution"]["action_claim_count"], 0)
        self.assertEqual(damaged["technical_execution"]["side_effect_count"], 0)

        duplicate = CASES["ORS-004"]["expected"]
        self.assertTrue(duplicate["business_outcome"]["returned_original_outcome"])
        self.assertEqual(duplicate["technical_execution"]["action_claim_count"], 1)
        self.assertEqual(duplicate["technical_execution"]["terminal_event_count"], 1)
        self.assertFalse(duplicate["technical_execution"]["duplicate_terminal_event_emitted"])

        recovery = CASES["ORS-005"]["expected"]["technical_execution"]
        self.assertEqual(
            recovery["termination_point"],
            "after_decision_commit_before_native_resume_acknowledgement",
        )
        self.assertTrue(recovery["native_continuation_reconciled"])
        self.assertTrue(recovery["stored_decision_reused"])
        self.assertTrue(recovery["original_decision_audit_preserved"])
        self.assertEqual(recovery["action_claim_count"], 1)

    def test_policy_evidence_failures_are_explicit_and_fail_closed(self):
        expected_errors = {
            "ORS-006": "policy_evidence_missing",
            "ORS-007": "policy_evidence_conflict",
            "ORS-008": "policy_evidence_invalid",
        }
        for case_id, error in expected_errors.items():
            with self.subTest(case=case_id):
                expected = CASES[case_id]["expected"]
                business = expected["business_outcome"]
                technical = expected["technical_execution"]
                self.assertFalse(business["proposal_authoritative"])
                self.assertIsNone(business["proposed_action"])
                self.assertEqual(business["state"], "failed")
                self.assertEqual(business["error"], error)
                self.assertEqual(business["verified_actions"], [])
                self.assertEqual(technical["action_claim_count"], 0)
                self.assertEqual(technical["side_effect_count"], 0)

        variants = CASES["ORS-008"]["expected"]["technical_execution"]["invalid_variants_checked"]
        self.assertEqual(variants, ["digest-invalid", "expired", "non-applicable"])
        self.assertEqual(CASES["ORS-006"]["input"]["policy_evidence"], [])
        self.assertEqual(len(CASES["ORS-007"]["input"]["policy_evidence"]), 2)
        self.assertNotEqual(
            CASES["ORS-007"]["input"]["policy_evidence"][0]["asserted_action"],
            CASES["ORS-007"]["input"]["policy_evidence"][1]["asserted_action"],
        )

    def test_unauthorized_decisions_remain_pending_and_auditable(self):
        expected = CASES["ORS-009"]["expected"]
        business = expected["business_outcome"]
        technical = expected["technical_execution"]
        self.assertEqual(business["error"], "authorization_denied")
        self.assertEqual(business["state"], "awaiting_approval")
        self.assertEqual(business["decision"], "pending")
        self.assertEqual(business["verified_actions"], [])
        self.assertEqual(technical["denied_actors"], ["REVIEWER-B", "USER-B"])
        self.assertEqual(technical["authorization_denial_count"], 2)
        self.assertTrue(technical["denial_privacy_safe"])
        self.assertTrue(technical["denial_auditable"])
        self.assertEqual(technical["side_effect_count"], 0)

    @unittest.skipUnless(
        os.environ.get("ORDER_RESOLUTION_ADAPTER"),
        "Order Resolution application adapter was not selected.",
    )
    def test_application_against_order_resolution_cases(self):
        adapter = os.environ["ORDER_RESOLUTION_ADAPTER"]
        command = [sys.executable, adapter] if Path(adapter).suffix.lower() == ".py" else [adapter]
        for case in GOLDEN["cases"]:
            with self.subTest(case=case["id"]):
                request = {"scenario_set": CONTRACT["scenario_set"], "case": case}
                process = subprocess.run(
                    command,
                    input=json.dumps(request),
                    text=True,
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                actual = json.loads(process.stdout)
                assert_subset(self, case["expected"], actual)


if __name__ == "__main__":
    unittest.main()
