"""Validate the synthetic scenario and, when selected, the real application adapter."""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "order-adjustment"
CASES = json.loads((SCENARIO / "golden-cases.json").read_text())


class GoldenScenarioTests(unittest.TestCase):
    def test_scenario_contract_and_traceability(self):
        contract = json.loads((SCENARIO / "verification-contract.json").read_text())
        schema = json.loads((ROOT / "contracts/verification-contract.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(contract)
        ids = [case["id"] for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        checks = {check["id"] for requirement in contract["requirements"] for check in requirement["checks"]}
        for case in CASES:
            with self.subTest(case=case["id"]):
                self.assertTrue(set(case["checks"]).issubset(checks))
                self.assertTrue(case["explanation_contains"])
                self.assertTrue(case["explanation_excludes"])
        self.assertEqual({check for case in CASES for check in case["checks"]}, checks)
        self.assertTrue({"pending", "approved", "rejected", "unauthorized", "replay", "restart",
                         "action-failure", "wrong-case-approval", "optional-hint"}.issubset(ids))

    def test_unapproved_example_is_schema_valid_and_baseline_pinned(self):
        for name in ("input", "trust"):
            schema = json.loads((ROOT / f"contracts/readiness-{name}.schema.json").read_text())
            Draft202012Validator.check_schema(schema)
            instance = json.loads((SCENARIO / f"example-{name}.json").read_text())
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)
        trust = json.loads((SCENARIO / "example-trust.json").read_text())
        self.assertEqual(trust["baseline_sha256"],
                         hashlib.sha256((SCENARIO / "verification-contract.json").read_bytes()).hexdigest())
        self.assertEqual(trust["keys"], [])

    @unittest.skipUnless(os.environ.get("SCENARIO_ADAPTER"), "Synthetic application adapter was not selected.")
    def test_application_against_golden_cases(self):
        adapter = os.environ["SCENARIO_ADAPTER"]
        command = [sys.executable, adapter] if Path(adapter).suffix.lower() == ".py" else [adapter]
        self.case_actuals = {}
        for case in CASES:
            with self.subTest(case=case["id"]):
                process = subprocess.run(command, input=json.dumps(case["input"]), text=True,
                                         capture_output=True, timeout=60, check=True)
                actual = json.loads(process.stdout)
                self.case_actuals[case["id"]] = actual
                for key, value in case["expected"].items():
                    self.assertEqual(actual[key], value)
                explanation = actual["explanation"].lower()
                for fact in case["explanation_contains"]:
                    self.assertIn(fact.lower(), explanation)
                for prohibited in case["explanation_excludes"]:
                    self.assertNotIn(prohibited.lower(), explanation)
                self.assertTrue(actual["correlation_id"])
                self.assertIn(actual["correlation_id"].lower(), explanation)


if __name__ == "__main__":
    unittest.main()
