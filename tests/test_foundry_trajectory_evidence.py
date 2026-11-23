import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.capture_foundry_trajectory_evidence import capture


class FoundryTrajectoryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=".")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.evidence = self.root / "hosted.json"
        self.output = self.root / "foundry.json"
        self.correlations = [
            {
                "request_id": "10000000-0000-4000-8000-000000000001",
                "case_id": "20000000-0000-4000-8000-000000000002",
                "trace_id": "1234567890abcdef1234567890abcdef",
                "hosted_phase": "start",
                "conversation_id": "conversation-1",
                "hosted_agent_name": "order-resolution",
                "hosted_agent_version": "2",
            },
            {
                "request_id": "10000000-0000-4000-8000-000000000003",
                "case_id": "20000000-0000-4000-8000-000000000002",
                "trace_id": "2234567890abcdef1234567890abcdef",
                "hosted_phase": "resume",
                "conversation_id": "conversation-1",
                "hosted_agent_name": "order-resolution",
                "hosted_agent_version": "2",
            },
        ]
        self.evidence.write_text(
            json.dumps(
                {
                    "source_revision": "source-123",
                    "deployment_revision": "deployment-123",
                    "environment": "synthetic-azure",
                    "started_at": "2026-11-22T20:00:00Z",
                    "correlations": self.correlations,
                }
            ),
            encoding="utf-8",
        )

    def test_exact_foundry_roots_produce_revision_bound_evidence(self):
        rows = [
            {
                "trace_id": item["trace_id"],
                "span_id": f"{index}" * 16,
                "parent_id": "",
                "conversation_id": item["conversation_id"],
                "agent_name": item["hosted_agent_name"],
                "agent_version": item["hosted_agent_version"],
                "foundry_marker": "hosted-agent-id",
            }
            for index, item in enumerate(self.correlations, start=1)
        ]
        with (
            patch(
                "scripts.capture_foundry_trajectory_evidence._azure_cli",
                return_value="az.cmd",
            ),
            patch(
                "scripts.capture_foundry_trajectory_evidence.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(rows),
                    stderr="",
                ),
            ) as run,
        ):
            artifact = capture(
                self.evidence,
                "workspace-id",
                self.output,
                source_revision="source-123",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
                attempts=1,
                wait_seconds=0,
            )
        self.assertEqual(artifact["outcome"], "passed")
        self.assertEqual(
            artifact["trace_ids"],
            sorted(item["trace_id"] for item in self.correlations),
        )
        command = run.call_args.args[0]
        self.assertEqual(command[0], "az.cmd")
        self.assertIn("invoke_agent", command[command.index("--analytics-query") + 1])

    def test_missing_foundry_root_never_produces_passing_evidence(self):
        with (
            patch(
                "scripts.capture_foundry_trajectory_evidence._azure_cli",
                return_value="az",
            ),
            patch(
                "scripts.capture_foundry_trajectory_evidence.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="[]", stderr=""),
            ),
            self.assertRaisesRegex(RuntimeError, "not visible"),
        ):
            capture(
                self.evidence,
                "workspace-id",
                self.output,
                source_revision="source-123",
                deployment_revision="deployment-123",
                environment="synthetic-azure",
                attempts=1,
                wait_seconds=0,
            )
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
