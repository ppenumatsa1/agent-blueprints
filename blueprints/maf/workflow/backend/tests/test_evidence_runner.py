import os
import unittest
from unittest.mock import patch

from tests.evidence_runner import CRASH_TESTS, RecordedResult, _failure, grounded_explanation, summarize


class EvidenceNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.contract = {"requirements": [{"checks": [{"id": "CHECK-RECOVERY"}]}]}
        self.cases = [{"id": "restart", "checks": ["CHECK-RECOVERY"], "input": {}}]
        self.crashes = {name: {"outcome": "passed"} for name in CRASH_TESTS}

    def test_failed_or_missing_evidence_is_never_promoted_to_pass(self):
        failed = {"restart": {"outcome": "failed", "failure": {"message": "actual failure"}}}
        self.assertEqual(
            summarize(self.contract, self.cases, failed, self.crashes, [])["CHECK-RECOVERY"]["outcome"],
            "failed",
        )
        observed = {"restart": {"outcome": "passed", "actual": {"state": "completed"}}}
        missing_crash = {CRASH_TESTS[0]: {"outcome": "passed"}}
        self.assertEqual(
            summarize(self.contract, self.cases, observed, missing_crash, [])["CHECK-RECOVERY"]["outcome"],
            "unverified",
        )
        self.assertEqual(
            summarize(self.contract, self.cases, observed, self.crashes, [])["CHECK-RECOVERY"]["outcome"],
            "passed",
        )
        self.assertEqual(
            summarize(self.contract, self.cases, {"restart": {"outcome": "passed"}}, self.crashes, [])
            ["CHECK-RECOVERY"]["outcome"],
            "unverified",
        )

    def test_retained_failure_redacts_database_credentials(self):
        dsn = "postgresql://test:secret%21@localhost/test"
        with patch.dict(os.environ, {"MAF_TEST_DATABASE_URL": dsn}):
            exception = RuntimeError(f"Unable to connect to {dsn}; password secret!")
            record = _failure((RuntimeError, exception, None))
        self.assertNotIn(dsn, record["message"])
        self.assertNotIn("secret!", record["message"])
        self.assertEqual(record["type"], "RuntimeError")

    def test_traceability_subtest_failure_is_not_overwritten_by_a_passing_case(self):
        class Fixture(unittest.TestCase):
            def test_traceability(self):
                with self.subTest(case="restart"):
                    self.fail("Traceability failed.")

            def test_application_against_golden_cases(self):
                self.case_actuals = {"restart": {"state": "completed"}}
                with self.subTest(case="restart"):
                    pass

        result = RecordedResult()
        unittest.TestSuite([
            Fixture("test_traceability"), Fixture("test_application_against_golden_cases")
        ]).run(result)
        self.assertEqual(result.cases["restart"]["outcome"], "passed")
        self.assertEqual(result.suite_errors[0]["outcome"], "failed")
        self.assertEqual(
            summarize(self.contract, self.cases, result.cases, self.crashes, result.suite_errors)
            ["CHECK-RECOVERY"]["outcome"],
            "failed",
        )

    def test_explanation_rejects_unsupported_facts(self):
        case = {"input": {"case_id": "CASE-TEST", "amount": 120}}
        actual = {
            "decision": "approved",
            "state": "completed",
            "correlation_id": "synthetic-id",
            "explanation": (
                "Case CASE-TEST proposes a synthetic adjustment of 120 units. "
                "Adjustments over 100 units require approval. Approval is approved. "
                "Correlation ID: synthetic-id."
            ),
        }
        self.assertTrue(grounded_explanation(case, actual))
        actual["explanation"] += " An unsupported fact."
        self.assertFalse(grounded_explanation(case, actual))

    def test_fixture_explanation_and_hint_do_not_prove_agent_or_browser_checks(self):
        case = {
            "id": "hint",
            "checks": ["CHECK-EXPLANATION", "CHECK-HINT"],
            "input": {"case_id": "CASE-TEST", "amount": 120},
        }
        actual = {
            "decision": "pending",
            "state": "pending",
            "correlation_id": "synthetic-id",
            "explanation": (
                "Case CASE-TEST proposes a synthetic adjustment of 120 units. "
                "Adjustments over 100 units require approval. Approval is pending. "
                "Correlation ID: synthetic-id."
            ),
            "hint": "Approval is pending.",
        }
        contract = {"requirements": [{"checks": [{"id": "CHECK-EXPLANATION"}, {"id": "CHECK-HINT"}]}]}
        observed = {"hint": {"outcome": "passed", "actual": actual}}
        results = summarize(contract, [case], observed, {}, [])
        self.assertEqual(results["CHECK-EXPLANATION"]["outcome"], "unverified")
        self.assertEqual(results["CHECK-HINT"]["outcome"], "unverified")
        actual["explanation"] += " An invented fact."
        self.assertEqual(summarize(contract, [case], observed, {}, [])["CHECK-EXPLANATION"]["outcome"], "failed")


if __name__ == "__main__":
    unittest.main()
