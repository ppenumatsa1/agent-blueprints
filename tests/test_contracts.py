import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
EXAMPLES = CONTRACTS / "examples"
SCHEMA_NAMES = ("blueprint-manifest", "verification-contract", "readiness-report")
VALID_EXAMPLES = {
    "blueprint-manifest": ("blueprint-manifest.valid.json",),
    "verification-contract": ("verification-contract.valid.json",),
    "readiness-report": (
        "readiness-report.unverified.valid.json",
        "readiness-report.passed.valid.json",
    ),
}


def load_json(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


class ContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            name: load_json(CONTRACTS / f"{name}.schema.json") for name in SCHEMA_NAMES
        }
        cls.validators = {
            name: Draft202012Validator(schema, format_checker=FormatChecker())
            for name, schema in cls.schemas.items()
        }

    def assert_valid(self, schema_name, document):
        errors = list(self.validators[schema_name].iter_errors(document))
        self.assertFalse(errors, "\n".join(error.message for error in errors))

    def assert_invalid(self, schema_name, document):
        self.assertTrue(list(self.validators[schema_name].iter_errors(document)))

    def test_schemas_are_valid_draft_2020_12(self):
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(schema)

    def test_valid_and_invalid_examples(self):
        for name in SCHEMA_NAMES:
            for filename in VALID_EXAMPLES[name]:
                with self.subTest(example=filename):
                    self.assert_valid(name, load_json(EXAMPLES / filename))
            filename = f"{name}.invalid.json"
            with self.subTest(example=filename):
                self.assert_invalid(name, load_json(EXAMPLES / filename))

    def test_verified_hosting_requires_specific_execution_evidence(self):
        manifest = load_json(EXAMPLES / "blueprint-manifest.valid.json")
        manifest["framework"]["version"] = "synthetic-version"
        hosting = manifest["hosting"][0]
        hosting["compatibility"] = "verified"
        self.assert_invalid("blueprint-manifest", manifest)
        hosting["evidence"] = [{"kind": "test_run", "reference": "fixture://run"}]
        self.assert_invalid("blueprint-manifest", manifest)
        hosting["evidence"][0].update(revision="fixture-revision", environment="fixture")
        self.assert_valid("blueprint-manifest", manifest)
        hosting.pop("protocol")
        self.assert_invalid("blueprint-manifest", manifest)
        hosting["protocol"] = "responses"
        manifest["framework"].pop("version")
        self.assert_invalid("blueprint-manifest", manifest)

    def test_validated_blueprint_requires_verified_hosting(self):
        manifest = load_json(EXAMPLES / "blueprint-manifest.valid.json")
        manifest["status"] = "validated"
        self.assert_invalid("blueprint-manifest", manifest)

    def test_unsupported_hosting_requires_documentation(self):
        manifest = load_json(EXAMPLES / "blueprint-manifest.valid.json")
        hosting = manifest["hosting"][0]
        hosting["compatibility"] = "unsupported"
        self.assert_invalid("blueprint-manifest", manifest)
        hosting["evidence"] = [{"kind": "documentation", "reference": "fixture://docs"}]
        self.assert_valid("blueprint-manifest", manifest)

    def test_passed_check_requires_nonblank_evidence(self):
        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        check = report["results"][0]["check_results"][0]
        check.pop("evidence")
        self.assert_invalid("readiness-report", report)
        check["evidence"] = [{"kind": "test_report", "reference": "  "}]
        self.assert_invalid("readiness-report", report)

    def test_passed_requirement_requires_all_reported_checks_to_pass(self):
        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        result = report["results"][0]
        result.pop("check_results")
        self.assert_invalid("readiness-report", report)
        result["check_results"] = [
            {"check_id": "CHECK-001", "outcome": "failed", "reason": "Synthetic failure"}
        ]
        self.assert_invalid("readiness-report", report)

    def test_passed_gate_requires_blocking_results_to_pass(self):
        original = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        for status in ("failed", "unverified"):
            with self.subTest(status=status):
                report = copy.deepcopy(original)
                result = report["results"][1]
                result["gate"] = "blocking"
                result["status"] = status
                result["reason"] = "Synthetic missing or failing evidence"
                self.assert_invalid("readiness-report", report)
        report = copy.deepcopy(original)
        report["results"][0]["gate"] = "non_blocking"
        self.assert_invalid("readiness-report", report)
        report["gate_status"] = "unverified"
        self.assert_valid("readiness-report", report)

    def test_customer_validated_pass_requires_approval(self):
        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        report["target_maturity"] = "customer_validated"
        result = report["results"][1]
        result.update(
            gate="blocking",
            status="passed",
            check_results=[
                {
                    "check_id": "CHECK-002",
                    "outcome": "passed",
                    "evidence": [
                        {"kind": "evaluation_result", "reference": "fixture://evaluation"}
                    ],
                }
            ],
        )
        result.pop("reason")
        self.assert_invalid("readiness-report", report)
        report["customer_approval"] = {
            "decision": "rejected",
            "reviewer": "Synthetic reviewer",
            "reference": "fixture://approval",
            "decided_at": "2026-01-01T00:00:00Z",
        }
        self.assert_invalid("readiness-report", report)
        report["customer_approval"]["decision"] = "approved"
        self.assert_valid("readiness-report", report)

    def test_not_applicable_requires_documented_human_review(self):
        report = load_json(EXAMPLES / "readiness-report.unverified.valid.json")
        result = report["results"][0]
        result["gate"] = "not_applicable"
        result["status"] = "not_applicable"
        self.assert_invalid("readiness-report", report)
        result["applicability_review"] = {
            "reviewer": "Synthetic reviewer",
            "reference": "fixture://applicability-review",
        }
        self.assert_valid("readiness-report", report)
        result["gate"] = "blocking"
        self.assert_invalid("readiness-report", report)
        result["gate"] = "not_applicable"
        result["status"] = "unverified"
        self.assert_invalid("readiness-report", report)

    def test_dates_are_checked(self):
        report = load_json(EXAMPLES / "readiness-report.unverified.valid.json")
        report["assessed_at"] = "not-a-date"
        self.assert_invalid("readiness-report", report)

    def test_synthetic_reports_trace_to_contract(self):
        contract = load_json(EXAMPLES / "verification-contract.valid.json")
        requirements = contract["requirements"]
        requirements_by_id = {requirement["id"]: requirement for requirement in requirements}
        self.assertEqual(len(requirements), len(requirements_by_id))
        all_check_ids = [
            check["id"] for requirement in requirements for check in requirement["checks"]
        ]
        self.assertEqual(len(all_check_ids), len(set(all_check_ids)))

        for filename in VALID_EXAMPLES["readiness-report"]:
            with self.subTest(example=filename):
                report = load_json(EXAMPLES / filename)
                self.assertEqual(report["contract_id"], contract["contract_id"])
                self.assertEqual(report["contract_version"], contract["contract_version"])
                results = report["results"]
                results_by_id = {result["requirement_id"]: result for result in results}
                self.assertEqual(len(results), len(results_by_id))
                self.assertEqual(set(results_by_id), set(requirements_by_id))

                for requirement_id, result in results_by_id.items():
                    requirement = requirements_by_id[requirement_id]
                    self.assertEqual(
                        result["gate"], requirement["gates"][report["target_maturity"]]
                    )
                    if result["status"] == "passed":
                        expected = {check["id"]: check for check in requirement["checks"]}
                        actual = {check["check_id"]: check for check in result["check_results"]}
                        self.assertEqual(len(actual), len(result["check_results"]))
                        self.assertEqual(set(actual), set(expected))
                        for check_id, check in actual.items():
                            actual_types = {item["kind"] for item in check["evidence"]}
                            self.assertTrue(
                                set(expected[check_id]["evidence_types"]).issubset(actual_types)
                            )

                blocking = [result for result in results if result["gate"] == "blocking"]
                expected_gate = (
                    "failed"
                    if any(result["status"] == "failed" for result in blocking)
                    else "unverified"
                    if not blocking or any(result["status"] != "passed" for result in blocking)
                    else "passed"
                )
                self.assertEqual(report["gate_status"], expected_gate)


if __name__ == "__main__":
    unittest.main()
