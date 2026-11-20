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
        "readiness-report.production.valid.json",
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
        evidence = check.pop("evidence")
        self.assert_invalid("readiness-report", report)
        check["evidence"] = evidence
        evidence[0]["reference"] = "  "
        self.assert_invalid("readiness-report", report)

    def test_evidence_requires_revision_environment_timestamp_and_digest(self):
        original = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        for field in ("revision", "environment", "recorded_at", "sha256"):
            with self.subTest(field=field):
                report = copy.deepcopy(original)
                report["results"][0]["check_results"][0]["evidence"][0].pop(field)
                self.assert_invalid("readiness-report", report)
        report = copy.deepcopy(original)
        report["results"][0]["check_results"][0]["evidence"][0]["sha256"] = "not-a-digest"
        self.assert_invalid("readiness-report", report)
        report = copy.deepcopy(original)
        report["results"][0]["check_results"][0]["evidence"][0]["recorded_at"] = "not-a-date"
        self.assert_invalid("readiness-report", report)
        report = copy.deepcopy(original)
        report.pop("environment")
        self.assert_invalid("readiness-report", report)

    def test_check_requires_explicit_positive_freshness_policy(self):
        contract = load_json(EXAMPLES / "verification-contract.valid.json")
        check = contract["requirements"][0]["checks"][0]
        check.pop("evidence_max_age_seconds")
        self.assert_invalid("verification-contract", contract)
        check["evidence_max_age_seconds"] = 0
        self.assert_invalid("verification-contract", contract)

    def test_outdated_schema_versions_are_not_silently_accepted(self):
        for version in ("0.1.0", "0.2.0"):
            with self.subTest(version=version):
                contract = load_json(EXAMPLES / "verification-contract.valid.json")
                contract["schema_version"] = version
                self.assert_invalid("verification-contract", contract)
                report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
                report["schema_version"] = version
                self.assert_invalid("readiness-report", report)

    def test_producer_extensions_preserve_required_core_fields(self):
        contract = load_json(EXAMPLES / "verification-contract.valid.json")
        self.assert_valid("verification-contract", contract)
        contract["extensions"]["specification_studio"]["extra_context"] = "Synthetic"
        self.assert_valid("verification-contract", contract)
        contract["unrecognized_root_field"] = "Synthetic"
        self.assert_invalid("verification-contract", contract)
        contract.pop("unrecognized_root_field")
        contract.pop("contract_id")
        contract["extensions"]["specification_studio"]["contract_id"] = "SYNTHETIC-DEMO"
        self.assert_invalid("verification-contract", contract)

        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        report["extensions"] = {"producer": {"extra_context": "Synthetic"}}
        self.assert_valid("readiness-report", report)
        report["extensions"] = {"invalid namespace": {}}
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

    def test_unverified_requirement_cannot_hide_a_failed_check(self):
        report = load_json(EXAMPLES / "readiness-report.production.valid.json")
        report["results"][3]["status"] = "unverified"
        self.assert_invalid("readiness-report", report)

    def test_prototype_discloses_non_blocking_failures_and_unknowns(self):
        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        self.assert_valid("readiness-report", report)
        self.assertEqual(report["results"][2]["status"], "unverified")
        self.assertEqual(report["results"][2]["check_results"][0]["outcome"], "unverified")
        self.assertEqual(report["results"][3]["status"], "failed")
        self.assertEqual(report["results"][3]["check_results"][0]["outcome"], "failed")
        for field in ("assumptions", "incomplete_integrations", "limitations"):
            with self.subTest(field=field):
                incomplete = copy.deepcopy(report)
                incomplete.pop(field)
                self.assert_invalid("readiness-report", incomplete)

    def test_passed_gate_requires_all_blocking_results_to_pass(self):
        for filename in (
            "readiness-report.passed.valid.json",
            "readiness-report.production.valid.json",
        ):
            original = load_json(EXAMPLES / filename)
            blocking_indices = [
                index for index, result in enumerate(original["results"])
                if result["gate"] == "blocking"
            ]
            for index in blocking_indices:
                for status in ("failed", "unverified"):
                    with self.subTest(example=filename, result=index, status=status):
                        report = copy.deepcopy(original)
                        result = report["results"][index]
                        result["status"] = status
                        result["reason"] = "Synthetic missing or failing evidence"
                        result.pop("check_results")
                        self.assert_invalid("readiness-report", report)
        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        report["results"][0]["gate"] = "non_blocking"
        self.assert_invalid("readiness-report", report)
        report["gate_status"] = "unverified"
        self.assert_valid("readiness-report", report)

    def test_production_pass_requires_risk_acceptance_without_relabeling(self):
        original = load_json(EXAMPLES / "readiness-report.production.valid.json")
        result = original["results"][3]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["check_results"][0]["outcome"], "failed")
        self.assert_valid("readiness-report", original)
        for status in ("failed", "unverified"):
            with self.subTest(status=status):
                report = copy.deepcopy(original)
                result = report["results"][3]
                result["status"] = status
                result["check_results"][0]["outcome"] = status
                result["risk_acceptance"]["scope"]["requirement_status"] = status
                self.assert_valid("readiness-report", report)
                result.pop("risk_acceptance")
                self.assert_invalid("readiness-report", report)
        for field in (
            "decision", "reviewer", "reference", "decided_at", "expires_at",
            "rationale", "compensating_controls", "scope",
        ):
            with self.subTest(missing_field=field):
                report = copy.deepcopy(original)
                report["results"][3]["risk_acceptance"].pop(field)
                self.assert_invalid("readiness-report", report)
        for field in (
            "requirement_id", "check_ids", "requirement_status", "contract_sha256", "target_maturity",
            "source_revision", "environment",
        ):
            with self.subTest(missing_scope=field):
                report = copy.deepcopy(original)
                report["results"][3]["risk_acceptance"]["scope"].pop(field)
                self.assert_invalid("readiness-report", report)
        for field, value in (("decision", "rejected"), ("expires_at", "not-a-date")):
            with self.subTest(field=field):
                report = copy.deepcopy(original)
                report["results"][3]["risk_acceptance"][field] = value
                self.assert_invalid("readiness-report", report)
        report = copy.deepcopy(original)
        report["results"][3]["status"] = "passed"
        report["results"][3]["check_results"] = copy.deepcopy(
            original["results"][0]["check_results"]
        )
        self.assert_invalid("readiness-report", report)

    def test_critical_and_security_critical_classifications_are_explicit(self):
        original = load_json(EXAMPLES / "verification-contract.valid.json")
        for target in ("prototype", "production_candidate", "customer_validated"):
            with self.subTest(target=target):
                contract = copy.deepcopy(original)
                contract["requirements"][0]["gates"][target] = "non_blocking"
                self.assert_invalid("verification-contract", contract)
        contract = copy.deepcopy(original)
        contract["requirements"][0]["critical"] = False
        self.assert_invalid("verification-contract", contract)
        contract = copy.deepcopy(original)
        contract["requirements"][0]["domains"] = ["integration"]
        self.assert_invalid("verification-contract", contract)
        for field in ("critical", "security_critical", "domains"):
            with self.subTest(missing_field=field):
                contract = copy.deepcopy(original)
                contract["requirements"][0].pop(field)
                self.assert_invalid("verification-contract", contract)

    def test_production_control_applicability_needs_review(self):
        contract = load_json(EXAMPLES / "verification-contract.valid.json")
        contract.pop("production_controls")
        self.assert_valid("verification-contract", contract)
        contract = load_json(EXAMPLES / "verification-contract.valid.json")
        controls = contract["production_controls"]
        controls["security"]["applicability"] = "not_applicable"
        self.assert_invalid("verification-contract", contract)
        controls["security"]["applicability"] = "required"
        controls["integration"] = {"applicability": "not_applicable"}
        self.assert_invalid("verification-contract", contract)
        controls["integration"]["reason"] = "No external integrations in this fixture."
        controls["integration"]["review"] = {
            "reviewer": "Synthetic reviewer",
            "reference": "fixture://applicability-review",
        }
        self.assert_valid("verification-contract", contract)

    def test_accepted_risk_cannot_override_a_blocking_result(self):
        original = load_json(EXAMPLES / "readiness-report.production.valid.json")
        for status in ("failed", "unverified"):
            with self.subTest(status=status):
                report = copy.deepcopy(original)
                result = report["results"][0]
                result["status"] = status
                result["reason"] = "The critical check did not pass."
                result.pop("check_results")
                result["risk_acceptance"] = copy.deepcopy(
                    original["results"][3]["risk_acceptance"]
                )
                result["risk_acceptance"]["scope"]["requirement_id"] = "REQ-001"
                result["risk_acceptance"]["scope"]["check_ids"] = ["CHECK-001"]
                result["risk_acceptance"]["scope"]["requirement_status"] = status
                self.assert_invalid("readiness-report", report)

    def test_passed_gate_requires_contract_digest_and_approval(self):
        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        approval = report.pop("contract_approval")
        self.assert_invalid("readiness-report", report)
        report["contract_approval"] = approval
        approval["decision"] = "rejected"
        self.assert_invalid("readiness-report", report)
        approval["decision"] = "approved"
        report["contract_sha256"] = "not-a-digest"
        self.assert_invalid("readiness-report", report)

    def test_customer_validated_pass_requires_approval(self):
        report = load_json(EXAMPLES / "readiness-report.production.valid.json")
        report["target_maturity"] = "customer_validated"
        report["results"][3]["risk_acceptance"]["scope"]["target_maturity"] = "customer_validated"
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
        self.assert_valid("readiness-report", report)
        report = load_json(EXAMPLES / "readiness-report.passed.valid.json")
        result = report["results"][1]
        result["gate"] = "not_applicable"
        result["status"] = "unverified"
        result["reason"] = "Applicability review has not been verified."
        result.pop("check_results")
        self.assert_invalid("readiness-report", report)
        report["gate_status"] = "unverified"
        self.assert_valid("readiness-report", report)

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
                    expected = {check["id"]: check for check in requirement["checks"]}
                    checks = result.get("check_results", [])
                    actual = {check["check_id"]: check for check in checks}
                    self.assertEqual(len(actual), len(checks))
                    self.assertTrue(set(actual).issubset(expected))
                    if result["status"] == "passed":
                        self.assertEqual(set(actual), set(expected))
                    for check_id, check in actual.items():
                        if check["outcome"] == "passed":
                            actual_types = {item["kind"] for item in check["evidence"]}
                            self.assertTrue(
                                set(expected[check_id]["evidence_types"]).issubset(actual_types)
                            )
                        for item in check.get("evidence", []):
                            self.assertEqual(item["revision"], report["source_revision"])
                            self.assertEqual(item["environment"], report["environment"])
                    if "risk_acceptance" in result:
                        scope = result["risk_acceptance"]["scope"]
                        self.assertEqual(scope["requirement_id"], requirement_id)
                        self.assertEqual(scope["requirement_status"], result["status"])
                        self.assertEqual(
                            set(scope["check_ids"]),
                            {check["check_id"] for check in checks if check["outcome"] != "passed"},
                        )
                        for field in ("contract_sha256", "target_maturity", "source_revision", "environment"):
                            self.assertEqual(scope[field], report[field])

                if report["target_maturity"] != "prototype":
                    for domain, control in contract["production_controls"].items():
                        if control["applicability"] == "required":
                            self.assertTrue(any(
                                domain in requirement["domains"]
                                and requirement["gates"][report["target_maturity"]] == "blocking"
                                for requirement in requirements
                            ), domain)


if __name__ == "__main__":
    unittest.main()
