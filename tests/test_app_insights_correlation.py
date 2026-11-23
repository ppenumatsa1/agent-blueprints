import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.verify_app_insights_correlation import verify


class AppInsightsCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.which = patch(
            "scripts.verify_app_insights_correlation.shutil.which",
            return_value="az",
        )
        self.which.start()
        self.addCleanup(self.which.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.evidence = self.root / "hosted.json"
        self.output = self.root / "telemetry.json"
        self.pair = {
            "request_id": "10000000-0000-4000-8000-000000000001",
            "case_id": "20000000-0000-4000-8000-000000000002",
            "trace_id": "1234567890abcdef1234567890abcdef",
            "agent_version": "0.1.0",
            "deployment_revision": "deployment-123",
        }
        self.evidence.write_text(
            json.dumps(
                {
                    "source_revision": "source-123",
                    "deployment_revision": "deployment-123",
                    "environment": "synthetic-azure",
                    "started_at": "2026-11-22T20:00:00Z",
                    "correlations": [self.pair],
                }
            ),
            encoding="utf-8",
        )

    def result(self, *, exceptions=0):
        return Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        **self.pair,
                        "telemetry_count": 6,
                        "exception_count": exceptions,
                    }
                ]
            ),
            stderr="",
        )

    def test_exact_privacy_safe_pair_is_required(self):
        with patch(
            "scripts.verify_app_insights_correlation.subprocess.run",
            return_value=self.result(),
        ) as run:
            artifact = verify(
                self.evidence,
                "workspace-id",
                self.output,
                source_revision="source-123",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
            )
        self.assertEqual(artifact["outcome"], "passed")
        query = run.call_args.args[0]
        self.assertIn("AppRequests", query[-3])
        self.assertIn("Properties['blueprint.request.id']", query[-3])
        self.assertIn("'10000000-0000-4000-8000-000000000001'", query[-3])
        self.assertNotIn("message", query[-3].lower())

    def test_missing_pair_or_correlated_exception_never_passes(self):
        for result in (
            Mock(returncode=0, stdout="[]", stderr=""),
            self.result(exceptions=1),
        ):
            with (
                self.subTest(result=result.stdout),
                patch(
                    "scripts.verify_app_insights_correlation.subprocess.run",
                    return_value=result,
                ),
                self.assertRaises(RuntimeError),
            ):
                verify(
                    self.evidence,
                    "workspace-id",
                    self.output,
                    source_revision="source-123",
                    deployment_revision="deployment-123",
                    environment="synthetic-azure",
                )

    def test_workspace_resource_id_is_resolved_before_query(self):
        resource_id = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.OperationalInsights/workspaces/workspace"
        )
        resolved = Mock(returncode=0, stdout="customer-id\n", stderr="")
        with patch(
            "scripts.verify_app_insights_correlation.subprocess.run",
            side_effect=(resolved, self.result()),
        ) as run:
            artifact = verify(
                self.evidence,
                resource_id,
                self.output,
                source_revision="source-123",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
            )
        self.assertEqual(artifact["outcome"], "passed")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "az",
                "monitor",
                "log-analytics",
                "workspace",
                "show",
                "--ids",
                resource_id,
                "--query",
                "customerId",
                "--output",
                "tsv",
                "--only-show-errors",
            ],
        )
        query_command = run.call_args_list[1].args[0]
        self.assertEqual(
            query_command[query_command.index("--workspace") + 1],
            "customer-id",
        )

    def test_platform_azure_cli_launcher_is_used(self):
        with (
            patch(
                "scripts.verify_app_insights_correlation.shutil.which",
                return_value=r"C:\tools\az.cmd",
            ),
            patch(
                "scripts.verify_app_insights_correlation.subprocess.run",
                return_value=self.result(),
            ) as run,
        ):
            verify(
                self.evidence,
                "workspace-id",
                self.output,
                source_revision="source-123",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
            )
        self.assertEqual(run.call_args.args[0][0], r"C:\tools\az.cmd")

    def test_revision_mismatch_stops_before_query(self):
        with (
            patch("scripts.verify_app_insights_correlation.subprocess.run") as run,
            self.assertRaises(ValueError),
        ):
            verify(
                self.evidence,
                "workspace-id",
                self.output,
                source_revision="different",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
            )
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
