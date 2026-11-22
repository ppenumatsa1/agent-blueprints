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
            metadata = {
                "schema_version": "1.0.0",
                "source_revision": "source-123",
                "deployment_revision": "deployment-456",
                "environment": "synthetic-azure",
                "recorded_at": "2026-11-22T20:05:00Z",
            }
            artifacts = {}
            for name in ("active", "provider", "browser", "telemetry"):
                path = root / f"{name}.json"
                path.write_text(
                    json.dumps({**metadata, "outcome": "passed"}),
                    encoding="utf-8",
                )
                artifacts[name] = path
            failure = root / "failure.json"
            failure.write_text(
                json.dumps(
                    {
                        **metadata,
                        "scenarios": {
                            f"scenario-{number}": {"status": "passed"}
                            for number in range(1, 10)
                        },
                    }
                ),
                encoding="utf-8",
            )
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
                failure_injection=failure,
                telemetry=artifacts["telemetry"],
            )
            report = validate_release_evidence(output, root)
        self.assertEqual(manifest["dimensions"]["azure_runtime"]["status"], "passed")
        self.assertEqual(report["dimensions"]["azure_runtime"]["status"], "passed")
        self.assertEqual(report["dimensions"]["production"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
