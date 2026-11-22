import json
import tempfile
import unittest
from pathlib import Path

from readiness.release import validate_release_evidence
from scripts.build_release_evidence import build


class BuildReleaseEvidenceTests(unittest.TestCase):
    def implementation(self, root):
        implementation = root / "implementation"
        implementation.mkdir()
        metadata = {
            "source_revision": "source-123",
            "environment": "github-actions-generated-order-resolution",
            "recorded_at": "2026-11-22T20:00:00Z",
        }
        (implementation / "runner-results.json").write_text(
            json.dumps(
                {
                    **metadata,
                    "cases": {
                        f"ORS-{number:03d}": {"outcome": "passed"}
                        for number in range(1, 10)
                    },
                }
            ),
            encoding="utf-8",
        )
        for name in (
            "ORDER-RESOLUTION-TECHNICAL-EXECUTION.json",
            "ORDER-RESOLUTION-BUSINESS-OUTCOME.json",
        ):
            (implementation / name).write_text(
                json.dumps({**metadata, "outcome": "passed"}),
                encoding="utf-8",
            )
        return implementation

    def cloud_artifacts(self, root, *, active="passed", scenario="passed"):
        metadata = {
            "schema_version": "1.0.0",
            "source_revision": "source-123",
            "deployment_revision": "deployment-456",
            "environment": "synthetic-azure",
            "recorded_at": "2026-11-22T20:05:00Z",
        }
        artifacts = {}
        for name, outcome in (
            ("active", active),
            ("provider", "passed"),
            ("browser", "passed"),
            ("telemetry", "passed"),
        ):
            path = root / f"{name}.json"
            path.write_text(
                json.dumps({**metadata, "outcome": outcome}),
                encoding="utf-8",
            )
            artifacts[name] = path
        failure = root / "failure.json"
        scenarios = (
            {}
            if scenario == "empty"
            else {f"scenario-{number}": {"status": scenario} for number in range(1, 10)}
        )
        failure.write_text(
            json.dumps({**metadata, "scenarios": scenarios}),
            encoding="utf-8",
        )
        artifacts["failure"] = failure
        return artifacts

    def build_cloud(self, root, implementation, artifacts):
        output = root / "release-evidence.json"
        manifest = build(
            root,
            implementation,
            output,
            source_revision="source-123",
            deployment_revision="deployment-456",
            environment="synthetic-azure",
            agent_version="0.1.0",
            active_revision=artifacts["active"],
            provider_evaluation=artifacts["provider"],
            browser=artifacts["browser"],
            failure_injection=artifacts["failure"],
            telemetry=artifacts["telemetry"],
        )
        return output, manifest

    def test_local_evidence_passes_implementation_but_not_cloud_or_production(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            implementation = self.implementation(root)
            output = root / "release-evidence.json"
            manifest = build(
                root,
                implementation,
                output,
                source_revision="source-123",
                deployment_revision="deployment-456",
                environment="synthetic-azure",
                agent_version="0.1.0",
            )
            report = validate_release_evidence(output, root)
        self.assertEqual(manifest["dimensions"]["implementation"]["status"], "passed")
        self.assertEqual(
            manifest["dimensions"]["azure_runtime"]["status"], "unverified"
        )
        self.assertEqual(manifest["dimensions"]["production"]["status"], "blocked")
        self.assertEqual(report["dimensions"]["implementation"]["status"], "passed")
        self.assertEqual(report["overall_status"], "blocked")

    def test_complete_cloud_evidence_passes_azure_runtime_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            implementation = self.implementation(root)
            output, manifest = self.build_cloud(
                root,
                implementation,
                self.cloud_artifacts(root),
            )
            report = validate_release_evidence(output, root)
        self.assertEqual(manifest["dimensions"]["azure_runtime"]["status"], "passed")
        self.assertEqual(report["dimensions"]["azure_runtime"]["status"], "passed")
        self.assertEqual(report["dimensions"]["production"]["status"], "blocked")

    def test_explicit_cloud_failure_remains_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, manifest = self.build_cloud(
                root,
                self.implementation(root),
                self.cloud_artifacts(root, active="failed"),
            )
            report = validate_release_evidence(output, root)
        self.assertEqual(manifest["dimensions"]["azure_runtime"]["status"], "failed")
        self.assertEqual(report["dimensions"]["azure_runtime"]["status"], "failed")

    def test_blocked_and_empty_hosted_scenarios_do_not_pass(self):
        for scenario, expected in (("blocked", "blocked"), ("empty", "unverified")):
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                output, manifest = self.build_cloud(
                    root,
                    self.implementation(root),
                    self.cloud_artifacts(root, scenario=scenario),
                )
                report = validate_release_evidence(output, root)
            self.assertEqual(
                manifest["dimensions"]["azure_runtime"]["status"],
                expected,
            )
            self.assertEqual(
                report["dimensions"]["azure_runtime"]["status"],
                expected,
            )


if __name__ == "__main__":
    unittest.main()
