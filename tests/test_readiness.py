"""Acceptance tests for the local readiness contract, not an application test."""

import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from readiness.validator import InputError, validate


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-01-02T00:00:00Z"
REVISION = "synthetic-revision"
ENVIRONMENT = "synthetic-local"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ReadinessAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        cls.private = Path(cls.keys.name) / "private.pem"
        cls.public = Path(cls.keys.name) / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt",
                        "rsa_keygen_bits:2048", "-out", str(cls.private)],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls.private), "-pubout",
                        "-out", str(cls.public)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.contract = json.loads((ROOT / "contracts/examples/verification-contract.valid.json").read_text())
        self.contract_path = self.root / "contract.json"
        self.baseline_path = self.root / "baseline.json"
        self.input_path = self.root / "input.json"
        self.trust_path = self.root / "trust.json"
        self.public_path = self.root / "public.pem"
        self.public_path.write_bytes(self.public.read_bytes())
        self.save_contract()
        self.baseline_path.write_bytes(self.contract_path.read_bytes())
        self.trust = {
            "baseline_sha256": digest(self.baseline_path.read_bytes()),
            "keys": [{
                "id": "reviewer", "reviewer": "Synthetic reviewer",
                "public_key": "public.pem",
                "roles": ["contract", "risk", "applicability", "classification", "customer", "result"],
            }],
        }
        self.inputs = {
            "schema_version": "1.0.0",
            "context": {"target_maturity": "prototype", "source_revision": REVISION,
                        "environment": ENVIRONMENT, "assessed_at": NOW},
            "assumptions": ["Synthetic identities only."],
            "incomplete_integrations": [],
            "limitations": [],
            "results": [],
            "decisions": [],
        }
        for requirement in self.contract["requirements"]:
            for check in requirement["checks"]:
                self.add_result(check)
        self.approve_contract()

    def save_contract(self):
        write_json(self.contract_path, self.contract)

    def add_result(self, check, outcome="passed"):
        check_id = check["id"]
        record = {"check_id": check_id, "outcome": outcome, "source_revision": REVISION,
                  "environment": ENVIRONMENT, "recorded_at": NOW}
        filename = f"{check_id}.json"
        write_json(self.root / filename, record)
        evidence = []
        for kind in set(check["evidence_types"]) | {"test_report"}:
            evidence.append({"kind": kind, "reference": filename, "revision": REVISION,
                             "environment": ENVIRONMENT, "recorded_at": NOW,
                             "sha256": digest((self.root / filename).read_bytes())})
        self.inputs["results"].append({"check_id": check_id, "outcome": outcome,
                                       "reason": "Synthetic result", "evidence": evidence,
                                       "implementation_refs": ["src/synthetic.py"]})

    def sign(self, kind, scope, decision="approved", **extra):
        payload = {"key_id": "reviewer", "kind": kind, "decision": decision,
                   "reference": f"synthetic-{kind}", "decided_at": "2026-01-01T00:00:00Z",
                   "expires_at": "2026-01-03T00:00:00Z", "scope": scope, **extra}
        signature = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(self.private)],
            input=canonical(payload), check=True, capture_output=True,
        ).stdout
        self.inputs["decisions"].append({
            "payload": payload, "signature": base64.b64encode(signature).decode("ascii"),
        })

    def approve_contract(self):
        self.sign("contract", {"contract_sha256": digest(self.contract_path.read_bytes())})

    def attest_results(self):
        self.inputs["decisions"] = [decision for decision in self.inputs["decisions"]
                                    if decision["payload"]["kind"] != "result"]
        context = self.inputs["context"]
        for result in self.inputs["results"]:
            self.sign("result", {
                "contract_sha256": digest(self.contract_path.read_bytes()),
                "target_maturity": context["target_maturity"], "source_revision": context["source_revision"],
                "environment": context["environment"], "check_id": result["check_id"],
                "result_sha256": digest(canonical(result)),
            }, decision="attested")

    def run_validator(self, attest=True):
        if attest:
            self.attest_results()
        write_json(self.input_path, self.inputs)
        write_json(self.trust_path, self.trust)
        report = validate(self.contract_path, self.baseline_path, self.input_path,
                          self.trust_path, self.root)
        schema = json.loads((ROOT / "contracts/readiness-report.schema.json").read_text())
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
        self.assertFalse(errors, [error.message for error in errors])
        return report

    def test_prototype_passes_with_disclosed_nonblocking_failures_and_missing_results(self):
        self.inputs["results"] = self.inputs["results"][:1]
        self.add_result(self.contract["requirements"][3]["checks"][0], outcome="failed")
        self.inputs["limitations"].append("Optional checks not assessed or failed.")
        report = self.run_validator()
        self.assertEqual(report["gate_status"], "passed")
        self.assertEqual([r["status"] for r in report["results"]],
                         ["passed", "unverified", "unverified", "failed"])
        self.assertIn("Optional checks not assessed or failed.", report["limitations"])

    def test_blocking_failed_and_corrupted_or_stale_evidence_never_pass(self):
        for case in ("failed", "digest", "stale", "future", "revision", "environment",
                     "missing", "corroboration"):
            with self.subTest(case=case):
                original = copy.deepcopy(self.inputs)
                result = self.inputs["results"][0]
                if case == "failed":
                    result["outcome"] = "failed"
                elif case == "digest":
                    result["evidence"][0]["sha256"] = "0" * 64
                elif case == "stale":
                    result["evidence"][0]["recorded_at"] = "2025-12-31T23:59:59Z"
                elif case == "future":
                    result["evidence"][0]["recorded_at"] = "2026-01-02T00:00:01Z"
                elif case == "revision":
                    result["evidence"][0]["revision"] = "wrong"
                elif case == "environment":
                    result["evidence"][0]["environment"] = "wrong"
                elif case == "missing":
                    result["evidence"][0]["reference"] = "missing.json"
                else:
                    result["outcome"] = "passed"
                    write_json(self.root / "CHECK-001.json", {"outcome": "failed"})
                    for item in result["evidence"]:
                        item["sha256"] = digest((self.root / "CHECK-001.json").read_bytes())
                report = self.run_validator()
                self.assertNotEqual(report["gate_status"], "passed")
                self.assertEqual(report["results"][0]["status"],
                                 "failed" if case == "failed" else "unverified")
                self.inputs = original
                # Restore the artifact for the next subcase.
                record = {"check_id": "CHECK-001", "outcome": "passed",
                          "source_revision": REVISION, "environment": ENVIRONMENT,
                          "recorded_at": NOW}
                write_json(self.root / "CHECK-001.json", record)

    def test_missing_invalid_expired_and_revoked_contract_approval_are_unverified(self):
        original = copy.deepcopy(self.inputs["decisions"])
        for case in ("missing", "signature", "expired", "revoked", "wrong_digest", "rejected"):
            with self.subTest(case=case):
                self.inputs["decisions"] = copy.deepcopy(original)
                self.trust["keys"][0].pop("revoked_at", None)
                if case == "missing":
                    self.inputs["decisions"] = []
                elif case == "signature":
                    self.inputs["decisions"][0]["signature"] = base64.b64encode(b"invalid").decode()
                elif case == "expired":
                    self.inputs["decisions"] = []
                    self.sign("contract", {"contract_sha256": digest(self.contract_path.read_bytes())},
                              expires_at="2026-01-01T12:00:00Z")
                elif case == "revoked":
                    self.trust["keys"][0]["revoked_at"] = "2026-01-01T12:00:00Z"
                elif case == "wrong_digest":
                    self.inputs["decisions"] = []
                    self.sign("contract", {"contract_sha256": "0" * 64})
                else:
                    self.inputs["decisions"] = []
                    self.sign("contract", {"contract_sha256": digest(self.contract_path.read_bytes())},
                              decision="rejected")
                self.assertEqual(self.run_validator()["gate_status"], "unverified")

    def test_unknown_and_duplicate_checks_are_not_ignored(self):
        for result in (copy.deepcopy(self.inputs["results"][0]),
                       {"check_id": "UNKNOWN", "outcome": "passed", "evidence": []}):
            with self.subTest(result=result["check_id"]):
                self.inputs["results"].append(result)
                self.assertNotEqual(self.run_validator()["gate_status"], "passed")
                self.inputs["results"].pop()

    def test_critical_downgrade_and_unreviewed_applicability_do_not_pass(self):
        self.contract["requirements"][0]["critical"] = False
        self.contract["requirements"][0]["security_critical"] = False
        self.save_contract()
        self.inputs["decisions"] = []
        self.approve_contract()
        self.assertEqual(self.run_validator()["gate_status"], "unverified")
        self.contract["requirements"][1]["gates"]["prototype"] = "not_applicable"
        self.save_contract()
        self.inputs["decisions"] = []
        self.approve_contract()
        self.assertEqual(self.run_validator()["gate_status"], "unverified")

    def test_production_missing_controls_and_customer_approval_do_not_pass(self):
        self.inputs["context"]["target_maturity"] = "production_candidate"
        self.contract.pop("production_controls")
        self.save_contract()
        self.inputs["decisions"] = []
        self.approve_contract()
        self.assertNotEqual(self.run_validator()["gate_status"], "passed")
        self.contract["production_controls"] = {
            domain: {"applicability": "required"}
            for domain in ("security", "integration", "operations", "evaluation")
        }
        self.save_contract()
        self.inputs["decisions"] = []
        self.approve_contract()
        self.inputs["context"]["target_maturity"] = "customer_validated"
        self.assertNotEqual(self.run_validator()["gate_status"], "passed")

    def test_production_risk_acceptance_binds_actual_findings_and_never_relabels_them(self):
        self.inputs["context"]["target_maturity"] = "production_candidate"
        self.inputs["results"].pop()
        self.add_result(self.contract["requirements"][3]["checks"][0], outcome="failed")
        initial = self.run_validator()
        self.assertEqual(initial["gate_status"], "failed")
        adverse = initial["results"][3]
        scope = {
            "requirement_id": "REQ-004", "check_ids": ["CHECK-004"],
            "requirement_status": "failed", "contract_sha256": initial["contract_sha256"],
            "target_maturity": "production_candidate", "source_revision": REVISION,
            "environment": ENVIRONMENT, "finding_sha256": digest(canonical(adverse["check_results"])),
        }
        self.sign("risk", scope, decision="accepted", rationale="Synthetic review.",
                  compensating_controls=[])
        report = self.run_validator()
        self.assertEqual(report["gate_status"], "passed")
        self.assertEqual(report["results"][3]["status"], "failed")
        self.assertEqual(report["results"][3]["check_results"][0]["outcome"], "failed")
        self.inputs["results"][3]["reason"] = "A new finding"
        self.assertEqual(self.run_validator()["gate_status"], "failed")

    def test_expired_or_wrong_scope_risk_decisions_cannot_pass(self):
        self.inputs["context"]["target_maturity"] = "production_candidate"
        self.inputs["results"].pop()
        self.add_result(self.contract["requirements"][3]["checks"][0], outcome="failed")
        initial = self.run_validator()
        scope = {
            "requirement_id": "REQ-004", "check_ids": ["CHECK-004"],
            "requirement_status": "failed", "contract_sha256": initial["contract_sha256"],
            "target_maturity": "production_candidate", "source_revision": REVISION,
            "environment": ENVIRONMENT,
            "finding_sha256": digest(canonical(initial["results"][3]["check_results"])),
        }
        for variant in ("expired", "wrong_scope"):
            with self.subTest(variant=variant):
                self.inputs["decisions"] = [d for d in self.inputs["decisions"]
                                            if d["payload"]["kind"] != "risk"]
                revised = copy.deepcopy(scope)
                if variant == "wrong_scope":
                    revised["environment"] = "different"
                extra = {"expires_at": "2026-01-01T12:00:00Z"} if variant == "expired" else {}
                self.sign("risk", revised, decision="accepted", rationale="Synthetic review.",
                          compensating_controls=[], **extra)
                self.assertEqual(self.run_validator()["gate_status"], "failed")

    def test_production_unverified_nonblocking_result_needs_risk_acceptance(self):
        self.inputs["context"]["target_maturity"] = "production_candidate"
        self.inputs["results"].pop()
        initial = self.run_validator()
        self.assertEqual(initial["gate_status"], "unverified")
        adverse = initial["results"][3]
        self.sign("risk", {
            "requirement_id": "REQ-004", "check_ids": ["CHECK-004"],
            "requirement_status": "unverified", "contract_sha256": initial["contract_sha256"],
            "target_maturity": "production_candidate", "source_revision": REVISION,
            "environment": ENVIRONMENT, "finding_sha256": digest(canonical(adverse["check_results"])),
        }, decision="accepted", rationale="Synthetic acceptance.", compensating_controls=[])
        report = self.run_validator()
        self.assertEqual(report["gate_status"], "passed")
        self.assertEqual(report["results"][3]["status"], "unverified")

    def test_production_requires_relevant_control_check_not_just_domain_tag(self):
        self.inputs["context"]["target_maturity"] = "production_candidate"
        self.contract["requirements"][2]["checks"][0]["method"] = "manual"
        self.save_contract()
        self.inputs["decisions"] = []
        self.approve_contract()
        report = self.run_validator()
        self.assertEqual(report["gate_status"], "unverified")
        self.assertTrue(any("operations lacks" in message
                            for message in report["extensions"]["validator"]["diagnostics"]))

    def test_customer_approval_binds_results_and_context(self):
        self.inputs["context"]["target_maturity"] = "customer_validated"
        initial = self.run_validator()
        self.assertEqual(initial["gate_status"], "unverified")
        scope = {"contract_sha256": initial["contract_sha256"], "target_maturity": "customer_validated",
                 "source_revision": REVISION, "environment": ENVIRONMENT,
                 "results_sha256": digest(canonical(initial["results"]))}
        self.sign("customer", scope, rationale="Synthetic acceptance.")
        self.assertEqual(self.run_validator()["gate_status"], "passed")
        self.inputs["results"][0]["implementation_refs"] = ["src/changed.py"]
        self.assertEqual(self.run_validator()["gate_status"], "unverified")

    def test_freshness_boundary_is_inclusive(self):
        result = self.inputs["results"][0]
        record = {"check_id": "CHECK-001", "outcome": "passed", "source_revision": REVISION,
                  "environment": ENVIRONMENT, "recorded_at": "2026-01-01T00:00:00Z"}
        write_json(self.root / "CHECK-001.json", record)
        for item in result["evidence"]:
            item["recorded_at"] = record["recorded_at"]
            item["sha256"] = digest((self.root / "CHECK-001.json").read_bytes())
        self.assertEqual(self.run_validator()["gate_status"], "passed")

    def test_authorized_classification_and_applicability_decisions_are_separate(self):
        self.contract["requirements"][1]["gates"]["prototype"] = "not_applicable"
        self.save_contract()
        self.inputs["decisions"] = []
        self.approve_contract()
        contract_hash = digest(self.contract_path.read_bytes())
        self.sign("classification", {
            "baseline_sha256": self.trust["baseline_sha256"], "contract_sha256": contract_hash,
            "requirement_id": "REQ-002", "changes": ["prototype changed to not_applicable"],
        }, rationale="Synthetic classification review.")
        self.assertEqual(self.run_validator()["gate_status"], "unverified")
        self.sign("applicability", {
            "contract_sha256": contract_hash, "target_maturity": "prototype",
            "source_revision": REVISION, "environment": ENVIRONMENT, "requirement_id": "REQ-002",
        }, rationale="Synthetic scope excludes this requirement.")
        report = self.run_validator()
        self.assertEqual(report["gate_status"], "passed")
        self.assertEqual(report["results"][1]["status"], "not_applicable")

    def test_external_or_escaping_evidence_is_unverified(self):
        for reference in ("../outside.json", "https://example.invalid/report"):
            with self.subTest(reference=reference):
                original = self.inputs["results"][0]["evidence"][0]["reference"]
                self.inputs["results"][0]["evidence"][0]["reference"] = reference
                self.assertEqual(self.run_validator()["gate_status"], "unverified")
                self.inputs["results"][0]["evidence"][0]["reference"] = original

    def test_baseline_must_match_independent_trust_anchor(self):
        self.trust["baseline_sha256"] = "0" * 64
        with self.assertRaises(InputError):
            self.run_validator()

    def test_duplicate_contract_check_ids_are_invalid_input(self):
        self.contract["requirements"][1]["checks"][0]["id"] = "CHECK-001"
        self.save_contract()
        with self.assertRaises(InputError):
            self.run_validator()

    def test_passing_result_needs_a_scoped_authorized_producer_attestation(self):
        self.assertEqual(self.run_validator(attest=False)["gate_status"], "unverified")
        self.attest_results()
        self.inputs["results"][0]["implementation_refs"] = ["src/tampered.py"]
        self.assertEqual(self.run_validator(attest=False)["gate_status"], "unverified")
        self.assertEqual(self.run_validator()["gate_status"], "passed")

    def test_cli_writes_report_and_diagnostic_with_nonzero_exit(self):
        self.attest_results()
        write_json(self.input_path, self.inputs)
        write_json(self.trust_path, self.trust)
        command = [
            str(Path(__import__("sys").executable)), "-m", "readiness",
            "--contract", str(self.contract_path), "--baseline", str(self.baseline_path),
            "--input", str(self.input_path), "--trust", str(self.trust_path),
            "--evidence-root", str(self.root),
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["gate_status"], "passed")
        self.inputs["results"] = self.inputs["results"][1:]
        write_json(self.input_path, self.inputs)
        output = self.root / "report.json"
        result = subprocess.run(command + ["--output", str(output)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(output.read_text())["gate_status"], "unverified")
        self.contract_path.write_text("{", encoding="utf-8")
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error", json.loads(result.stdout))
        result = subprocess.run(command[:3], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", json.loads(result.stderr))


if __name__ == "__main__":
    unittest.main()
