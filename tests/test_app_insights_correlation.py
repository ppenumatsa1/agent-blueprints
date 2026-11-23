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
        self.foundry = self.root / "foundry.json"
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
        self.foundry.write_text(
            json.dumps(
                {
                    "evidence_kind": "foundry_trajectory_index",
                    "outcome": "passed",
                    "source_revision": "source-123",
                    "deployment_revision": "deployment-123",
                    "environment": "synthetic-azure",
                    "recorded_at": "2026-11-22T20:10:00Z",
                    "agent_name": "order-resolution",
                    "trace_ids": [self.pair["trace_id"]],
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

    def test_hosted_trace_requires_complete_graph_restart_link_and_foundry_visibility(
        self,
    ):
        start = {
            **self.pair,
            "hosted_phase": "start",
            "conversation_id": "conversation-1",
            "hosted_agent_name": "order-resolution",
            "hosted_agent_version": "2",
        }
        resume = {
            **self.pair,
            "request_id": "10000000-0000-4000-8000-000000000002",
            "trace_id": "2234567890abcdef1234567890abcdef",
            "hosted_phase": "resume",
            "conversation_id": "conversation-1",
            "hosted_agent_name": "order-resolution",
            "hosted_agent_version": "2",
        }
        self.evidence.write_text(
            json.dumps(
                {
                    "source_revision": "source-123",
                    "deployment_revision": "deployment-123",
                    "environment": "synthetic-azure",
                    "started_at": "2026-11-22T20:00:00Z",
                    "correlations": [start, resume],
                }
            ),
            encoding="utf-8",
        )
        self.foundry.write_text(
            json.dumps(
                {
                    "evidence_kind": "foundry_trajectory_index",
                    "outcome": "passed",
                    "source_revision": "source-123",
                    "deployment_revision": "deployment-123",
                    "environment": "synthetic-azure",
                    "recorded_at": "2026-11-22T20:10:00Z",
                    "agent_name": "order-resolution",
                    "trace_ids": [start["trace_id"], resume["trace_id"]],
                }
            ),
            encoding="utf-8",
        )

        def span_rows(item):
            root = {
                "table_name": "AppDependencies",
                "trace_id": item["trace_id"],
                "span_id": "1" * 16,
                "parent_id": "8" * 16,
                "span_name": "invoke_agent",
                "role_name": "order-resolution",
                "operation_name": "invoke_agent",
                "conversation_id": "conversation-1",
                "agent_name": "order-resolution",
                "agent_version": "2",
                "foundry_marker": "True",
                "deployment_revision": "deployment-123",
                "anchor_type": "app-owned-invoke-agent",
                "anchor_source": "azure.ai.agentserver.responses.create_span_hook",
                "remote_parent": "true",
                "workflow_stage": "",
                "link_trace_id": "",
                "link_span_id": "",
                "raw_content": 0,
            }
            api = {
                **root,
                "span_id": "2" * 16,
                "parent_id": "9" * 16,
                "span_name": "http.request",
                "role_name": "agent-blueprints.maf-workflow",
                "operation_name": "",
                "conversation_id": "",
                "agent_name": "",
                "agent_version": "",
                "foundry_marker": "",
                "deployment_revision": "",
                "anchor_type": "",
                "anchor_source": "",
                "remote_parent": "",
            }
            dependency = {
                **root,
                "span_id": "3" * 16,
                "parent_id": "2" * 16,
                "span_name": "POST /responses",
                "role_name": "agent-blueprints.maf-workflow",
                "operation_name": "",
            }
            native = [
                {
                    **root,
                    "span_id": f"{index:x}" * 16,
                    "parent_id": "1" * 16,
                    "span_name": name,
                    "operation_name": "",
                }
                for index, name in (
                    (4, "workflow.build"),
                    (5, "executor.process approval"),
                    (6, "invoke_workflow approval-workflow-v1"),
                    (10, "edge_group.process InternalEdgeGroup"),
                    (7, f"order_resolution.workflow.{item['hosted_phase']}"),
                )
            ]
            if item["hosted_phase"] == "resume":
                native[-1]["link_trace_id"] = start["trace_id"]
                native[-1]["link_span_id"] = "a" * 16
            return [api, dependency, root, *native]

        exact = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {**start, "telemetry_count": 8, "exception_count": 0},
                    {**resume, "telemetry_count": 8, "exception_count": 0},
                ]
            ),
            stderr="",
        )
        details = Mock(
            returncode=0,
            stdout=json.dumps(span_rows(start) + span_rows(resume)),
            stderr="",
        )
        with patch(
            "scripts.verify_app_insights_correlation.subprocess.run",
            side_effect=(exact, details),
        ):
            artifact = verify(
                self.evidence,
                "workspace-id",
                self.output,
                source_revision="source-123",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
                foundry_evidence=self.foundry,
            )
        self.assertEqual(artifact["outcome"], "passed")
        self.assertEqual(len(artifact["validated_hosted_traces"]), 2)
        self.assertEqual(
            {item["root_kind"] for item in artifact["validated_hosted_traces"]},
            {"app-owned-hook"},
        )
        self.assertEqual(
            {item["graph_mode"] for item in artifact["validated_hosted_traces"]},
            {"platform-parent-gap"},
        )
        self.assertEqual(
            {
                boundary["classification"]
                for item in artifact["validated_hosted_traces"]
                for boundary in item["boundary_classifications"]
            },
            {
                "expected-external-caller-boundary",
                "expected-agentserver-platform-parent-boundary",
            },
        )
        self.assertEqual(
            {
                item["external_parent_count"]
                for item in artifact["validated_hosted_traces"]
            },
            {2},
        )

        invalid_rows = span_rows(start) + span_rows(resume)
        variants = {
            "missing marker": [
                {
                    **row,
                    "anchor_type": (
                        "" if row["span_name"] == "invoke_agent" else row["anchor_type"]
                    ),
                }
                for row in invalid_rows
            ],
            "duplicate anchor": invalid_rows
            + [
                {
                    **span_rows(start)[2],
                    "span_id": "a" * 16,
                }
            ],
            "arbitrary hosted orphan": invalid_rows
            + [
                {
                    **span_rows(start)[3],
                    "span_id": "b" * 16,
                    "parent_id": "c" * 16,
                    "span_name": "unexpected.hosted.orphan",
                }
            ],
        }
        for label, rows in variants.items():
            with (
                self.subTest(label=label),
                patch(
                    "scripts.verify_app_insights_correlation.subprocess.run",
                    side_effect=(
                        exact,
                        Mock(
                            returncode=0,
                            stdout=json.dumps(rows),
                            stderr="",
                        ),
                    ),
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
                    foundry_evidence=self.foundry,
                )

    def test_hosted_trace_never_passes_without_foundry_evidence(self):
        value = json.loads(self.evidence.read_text(encoding="utf-8"))
        value["correlations"][0].update(
            {
                "hosted_phase": "start",
                "conversation_id": "conversation-1",
                "hosted_agent_name": "order-resolution",
                "hosted_agent_version": "2",
            }
        )
        self.evidence.write_text(json.dumps(value), encoding="utf-8")
        with (
            patch("scripts.verify_app_insights_correlation.subprocess.run") as run,
            self.assertRaises(ValueError),
        ):
            verify(
                self.evidence,
                "workspace-id",
                self.output,
                source_revision="source-123",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
            )
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
