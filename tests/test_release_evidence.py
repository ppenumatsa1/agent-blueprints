import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from readiness.release import validate_release_evidence
from readiness.validator import InputError


REVISION = "revision-123"
DEPLOYMENT = "deployment-456"
ENVIRONMENT = "synthetic-azure"
RECORDED_AT = "2026-11-22T21:00:00Z"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def artifact(self, name, *, deployment_revision=None):
        value = {
            "source_revision": REVISION,
            "environment": ENVIRONMENT,
            "recorded_at": RECORDED_AT,
            "outcome": "passed",
        }
        if deployment_revision is not None:
            value["deployment_revision"] = deployment_revision
        path = self.root / name
        write_json(path, value)
        return path

    def evidence(self, check_id, kind, path, *, deployment_revision=None):
        return {
            "check_id": check_id,
            "kind": kind,
            "reference": path.name,
            "source_revision": REVISION,
            "deployment_revision": deployment_revision,
            "environment": ENVIRONMENT,
            "recorded_at": RECORDED_AT,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def manifest(self, *, deployment_revision=None):
        local = self.artifact("local.json")
        return {
            "schema_version": "1.0.0",
            "authority": "diagnostic_non_authorizing",
            "source_revision": REVISION,
            "environment": ENVIRONMENT,
            "agent_version": "0.1.0",
            "deployment_revision": deployment_revision,
            "recorded_at": RECORDED_AT,
            "dimensions": {
                "implementation": {
                    "status": "passed",
                    "reason": "Local checks passed.",
                    "required_checks": ["LOCAL-TESTS"],
                    "evidence": [
                        self.evidence(
                            "LOCAL-TESTS",
                            "local_test",
                            local,
                            deployment_revision=deployment_revision,
                        )
                    ],
                    "blockers": [],
                },
                "azure_runtime": {
                    "status": "unverified",
                    "reason": "Cloud checks were not run.",
                    "required_checks": ["ACTIVE-REVISION"],
                    "evidence": [],
                    "blockers": [],
                },
                "production": {
                    "status": "blocked",
                    "reason": "Cloud readiness is required.",
                    "required_checks": ["HUMAN-REVIEW"],
                    "evidence": [],
                    "blockers": ["Azure runtime readiness is unverified."],
                },
            },
        }

    def pass_runtime(self, manifest):
        runtime = manifest["dimensions"]["azure_runtime"]
        runtime["status"] = "passed"
        runtime["reason"] = "Every hosted check passed."
        runtime["required_checks"] = []
        runtime["evidence"] = []
        for index, kind in enumerate(
            (
                "active_revision",
                "hosted_test",
                "evaluation_result",
                "browser_test",
                "failure_injection",
                "telemetry_query",
            )
        ):
            check_id = f"RUNTIME-{index}"
            artifact = self.artifact(f"{kind}.json", deployment_revision=DEPLOYMENT)
            if kind in {"hosted_test", "failure_injection"}:
                write_json(
                    artifact,
                    {
                        "source_revision": REVISION,
                        "deployment_revision": DEPLOYMENT,
                        "environment": ENVIRONMENT,
                        "recorded_at": RECORDED_AT,
                        "scenarios": {"bounded-fault": {"status": "passed"}},
                    },
                )
            runtime["required_checks"].append(check_id)
            runtime["evidence"].append(
                self.evidence(
                    check_id,
                    kind,
                    artifact,
                    deployment_revision=DEPLOYMENT,
                )
            )

    def validate(self, manifest):
        path = self.root / "release-evidence.json"
        write_json(path, manifest)
        return validate_release_evidence(path, self.root)

    def test_local_pass_does_not_promote_cloud_or_production(self):
        report = self.validate(self.manifest())
        self.assertEqual(report["dimensions"]["implementation"]["status"], "passed")
        self.assertEqual(report["dimensions"]["azure_runtime"]["status"], "unverified")
        self.assertEqual(report["dimensions"]["production"]["status"], "blocked")
        self.assertEqual(report["overall_status"], "blocked")

    def test_azure_pass_requires_exact_revision_and_every_runtime_evidence_kind(self):
        manifest = self.manifest(deployment_revision=DEPLOYMENT)
        self.pass_runtime(manifest)
        report = self.validate(manifest)
        self.assertEqual(report["dimensions"]["azure_runtime"]["status"], "passed")

        tampered = copy.deepcopy(manifest)
        tampered["dimensions"]["azure_runtime"]["evidence"][0][
            "deployment_revision"
        ] = "different"
        downgraded = self.validate(tampered)
        self.assertEqual(
            downgraded["dimensions"]["azure_runtime"]["status"],
            "unverified",
        )

    def test_production_pass_requires_dependencies_and_review_evidence(self):
        manifest = self.manifest()
        production = manifest["dimensions"]["production"]
        production.update(
            status="passed",
            reason="Claimed production readiness.",
            blockers=[],
        )
        production["required_checks"] = ["SECURITY", "COST", "REVIEW"]
        for check_id, kind in (
            ("SECURITY", "security_report"),
            ("COST", "cost_report"),
            ("REVIEW", "human_review"),
        ):
            artifact = self.artifact(f"{kind}.json")
            production["evidence"].append(self.evidence(check_id, kind, artifact))
        report = self.validate(manifest)
        self.assertEqual(report["dimensions"]["production"]["status"], "blocked")
        self.assertTrue(report["dimensions"]["production"]["issues"])

    def test_self_authored_production_evidence_is_never_authorizing(self):
        manifest = self.manifest(deployment_revision=DEPLOYMENT)
        self.pass_runtime(manifest)
        production = manifest["dimensions"]["production"]
        production.update(
            status="passed",
            reason="Self-authored production claim.",
            blockers=[],
            required_checks=["SECURITY", "COST", "REVIEW"],
        )
        for check_id, kind in (
            ("SECURITY", "security_report"),
            ("COST", "cost_report"),
            ("REVIEW", "human_review"),
        ):
            artifact = self.artifact(
                f"self-authored-{kind}.json",
                deployment_revision=DEPLOYMENT,
            )
            production["evidence"].append(
                self.evidence(
                    check_id,
                    kind,
                    artifact,
                    deployment_revision=DEPLOYMENT,
                )
            )
        report = self.validate(manifest)
        self.assertEqual(report["dimensions"]["implementation"]["status"], "passed")
        self.assertEqual(report["dimensions"]["azure_runtime"]["status"], "passed")
        self.assertEqual(report["dimensions"]["production"]["status"], "blocked")
        self.assertIn(
            "diagnostic and non-authorizing",
            " ".join(report["dimensions"]["production"]["issues"]),
        )
        self.assertEqual(report["overall_status"], "blocked")

    def test_explicit_failed_dimension_is_not_downgraded(self):
        manifest = self.manifest(deployment_revision=DEPLOYMENT)
        manifest["dimensions"]["azure_runtime"].update(
            status="failed",
            reason="A hosted gate explicitly failed.",
        )
        report = self.validate(manifest)
        self.assertEqual(report["dimensions"]["azure_runtime"]["status"], "failed")
        self.assertEqual(report["overall_status"], "failed")

    def test_schema_rejects_passed_dimension_without_evidence(self):
        manifest = self.manifest()
        manifest["dimensions"]["implementation"]["evidence"] = []
        with self.assertRaises(InputError):
            self.validate(manifest)

    def test_hash_or_artifact_revision_mismatch_never_passes(self):
        manifest = self.manifest()
        evidence = manifest["dimensions"]["implementation"]["evidence"][0]
        evidence["sha256"] = "0" * 64
        report = self.validate(manifest)
        self.assertEqual(report["dimensions"]["implementation"]["status"], "unverified")
        self.assertTrue(report["dimensions"]["implementation"]["issues"])

    def test_failed_artifact_outcome_never_satisfies_a_passed_dimension(self):
        manifest = self.manifest()
        artifact = self.root / "local.json"
        failed = json.loads(artifact.read_text(encoding="utf-8"))
        failed["outcome"] = "failed"
        write_json(artifact, failed)
        manifest["dimensions"]["implementation"]["evidence"][0]["sha256"] = (
            hashlib.sha256(artifact.read_bytes()).hexdigest()
        )
        report = self.validate(manifest)
        self.assertEqual(report["dimensions"]["implementation"]["status"], "unverified")
        self.assertIn(
            "artifact does not report a passed outcome",
            report["dimensions"]["implementation"]["issues"][0],
        )


if __name__ == "__main__":
    unittest.main()
