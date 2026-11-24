import json
import os
import sys
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch
from uuid import uuid4

from tests.hosted_failure_runner import (
    AuthorizationFailure,
    HostedRecord,
    ReconciliationRequired,
    StaleApproval,
    TransientFailure,
    UnknownOutcome,
    UnsupportedScenario,
    _hosted_interruption,
    main,
    run_scenarios,
)


class FixtureHostedAdapter:
    source_revision = "source-123"
    deployment_revision = "deployment-456"
    target_kind = "synthetic-nonproduction"
    target_id = "synthetic-target"

    def __init__(self):
        self.records = {}
        self.keys = {}
        self.postgres_fault = False
        self.tool_timeout = False

    def create(self, idempotency_key, *, lose_ack=False):
        record = self.keys.get(idempotency_key)
        if record is None:
            record = HostedRecord(
                case_id=str(uuid4()),
                request_id=str(uuid4()),
                idempotency_key=idempotency_key,
                status="pending",
                technical_status="succeeded",
                business_outcome="pending",
                effect_count=0,
            )
            self.records[record.case_id] = record
            self.keys[idempotency_key] = record
        if lose_ack:
            raise UnknownOutcome("response acknowledgement lost")
        return record

    def lookup(self, idempotency_key):
        return self.keys[idempotency_key]

    def read(self, case_id):
        if self.postgres_fault:
            raise TransientFailure("postgres unavailable")
        return self.records[case_id]

    def approve(self, case_id, *, actor="authorized", request_id=None):
        record = self.records[case_id]
        if actor != "authorized":
            raise AuthorizationFailure("forbidden")
        if request_id != record.request_id:
            raise StaleApproval("stale")
        if self.tool_timeout:
            unknown = replace(
                record,
                status="approved",
                technical_status="unknown",
                business_outcome="approved",
                effect_count=1,
            )
            self.records[case_id] = unknown
            self.keys[record.idempotency_key] = unknown
            raise UnknownOutcome("effect acknowledgement timed out")
        if record.business_outcome == "completed":
            return record
        completed = replace(
            record,
            status="completed",
            technical_status="succeeded",
            business_outcome="completed",
            effect_count=1,
        )
        self.records[case_id] = completed
        self.keys[record.idempotency_key] = completed
        return completed

    def restart_api(self):
        return None

    def interrupt_host(self, case_id):
        record = self.records[case_id]
        interrupted = replace(record, technical_status="interrupted")
        self.records[case_id] = interrupted
        self.keys[record.idempotency_key] = interrupted

    def set_postgres_transient(self, enabled):
        self.postgres_fault = enabled

    def set_tool_timeout_after_effect(self, enabled):
        self.tool_timeout = enabled

    def retry(self, case_id):
        if self.records[case_id].technical_status == "unknown":
            raise ReconciliationRequired("reconcile first")
        return self.records[case_id]

    def reconcile(self, case_id):
        record = self.records[case_id]
        if record.technical_status == "interrupted":
            reconciled = replace(record, technical_status="succeeded")
        elif record.technical_status == "unknown":
            reconciled = replace(
                record,
                status="completed",
                technical_status="succeeded",
                business_outcome="completed",
            )
        else:
            reconciled = record
        self.records[case_id] = reconciled
        self.keys[record.idempotency_key] = reconciled
        return reconciled

    def correlations(self):
        return [
            {
                "request_id": record.request_id,
                "case_id": record.case_id,
                "trace_id": f"{index + 1:032x}",
                "agent_version": "0.1.0",
                "deployment_revision": self.deployment_revision,
            }
            for index, record in enumerate(self.records.values())
        ]


class HostedFailureRunnerTests(unittest.TestCase):
    def test_unsupported_hosted_interruption_is_blocked_without_hiding_other_results(self):
        result = run_scenarios(
            FixtureHostedAdapter(),
            source_revision="source-123",
            deployment_revision="deployment-456",
            environment="synthetic-hosted",
            target_kind="synthetic-nonproduction",
            target_id="synthetic-target",
        )
        self.assertEqual(len(result["scenarios"]), 9)
        self.assertEqual(result["scenarios"]["hosted_interruption"]["status"], "blocked")
        self.assertEqual(
            {
                name: item["status"]
                for name, item in result["scenarios"].items()
                if name != "hosted_interruption"
            },
            {name: "passed" for name in result["scenarios"] if name != "hosted_interruption"},
        )
        self.assertEqual(result["source_revision"], "source-123")
        self.assertEqual(result["deployment_revision"], "deployment-456")
        self.assertNotIn("synthetic-target", json.dumps(result))
        self.assertTrue(result["correlations"])

    def test_hosted_interruption_blocks_before_any_adapter_call(self):
        adapter = Mock()
        with self.assertRaises(UnsupportedScenario):
            _hosted_interruption(adapter)
        adapter.assert_not_called()
        self.assertEqual(adapter.mock_calls, [])

    def test_exact_active_revision_is_required(self):
        with self.assertRaisesRegex(ValueError, "source revision"):
            run_scenarios(
                FixtureHostedAdapter(),
                source_revision="different",
                deployment_revision="deployment-456",
                environment="synthetic-hosted",
                target_kind="synthetic-nonproduction",
                target_id="synthetic-target",
            )
        with self.assertRaisesRegex(ValueError, "deployment revision"):
            run_scenarios(
                FixtureHostedAdapter(),
                source_revision="source-123",
                deployment_revision="different",
                environment="synthetic-hosted",
                target_kind="synthetic-nonproduction",
                target_id="synthetic-target",
            )

    def test_synthetic_nonproduction_target_must_match_exactly(self):
        adapter = FixtureHostedAdapter()
        with self.assertRaisesRegex(ValueError, "synthetic nonproduction"):
            run_scenarios(
                adapter,
                source_revision="source-123",
                deployment_revision="deployment-456",
                environment="synthetic-hosted",
                target_kind="production",
                target_id="synthetic-target",
            )
        with self.assertRaisesRegex(ValueError, "approved target"):
            run_scenarios(
                adapter,
                source_revision="source-123",
                deployment_revision="deployment-456",
                environment="synthetic-hosted",
                target_kind="synthetic-nonproduction",
                target_id="different-target",
            )

    def test_runner_rejects_unsafe_target_before_loading_adapter(self):
        environment = {
            "MAF_HOSTED_FAILURE_ENABLED": "true",
            "MAF_HOSTED_FAILURE_ADAPTER": "unsafe:factory",
            "MAF_HOSTED_FAILURE_TARGET_KIND": "production",
            "MAF_HOSTED_FAILURE_TARGET_ID": "target-a",
            "MAF_HOSTED_FAILURE_EXPECTED_TARGET_ID": "target-a",
            "MAF_HOSTED_BASE_URL": "https://example.invalid",
            "SOURCE_REVISION": "source-123",
            "DEPLOYMENT_REVISION": "deployment-456",
            "EVIDENCE_ENVIRONMENT": "production",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(sys, "argv", ["hosted_failure_runner", "--output", "unused.json"]),
            patch("tests.hosted_failure_runner._load_adapter") as load_adapter,
        ):
            self.assertEqual(main(), 2)
        load_adapter.assert_not_called()

    def test_failures_record_only_exception_type_not_payload(self):
        adapter = FixtureHostedAdapter()

        def fail():
            raise RuntimeError("secret-canary")

        adapter.restart_api = fail
        result = run_scenarios(
            adapter,
            source_revision="source-123",
            deployment_revision="deployment-456",
            environment="synthetic-hosted",
            target_kind="synthetic-nonproduction",
            target_id="synthetic-target",
        )
        record = result["scenarios"]["api_restart"]
        self.assertEqual(record["status"], "failed")
        self.assertIn("RuntimeError", record["reason"])
        self.assertNotIn("secret-canary", str(result))

    def test_duplicate_approval_must_complete_one_effect(self):
        adapter = FixtureHostedAdapter()

        def no_op(case_id, *, actor="authorized", request_id=None):
            return adapter.records[case_id]

        adapter.approve = no_op
        result = run_scenarios(
            adapter,
            source_revision="source-123",
            deployment_revision="deployment-456",
            environment="synthetic-hosted",
            target_kind="synthetic-nonproduction",
            target_id="synthetic-target",
        )
        self.assertEqual(result["scenarios"]["duplicate_approval"]["status"], "failed")

    def test_correlations_cover_every_passed_scenario(self):
        adapter = FixtureHostedAdapter()
        adapter.correlations = lambda: [
            {
                "request_id": str(uuid4()),
                "case_id": str(uuid4()),
                "trace_id": "1" * 32,
                "agent_version": "0.1.0",
                "deployment_revision": adapter.deployment_revision,
            }
        ]
        with self.assertRaisesRegex(ValueError, "every passed scenario"):
            run_scenarios(
                adapter,
                source_revision="source-123",
                deployment_revision="deployment-456",
                environment="synthetic-hosted",
                target_kind="synthetic-nonproduction",
                target_id="synthetic-target",
            )

    def test_correlation_request_ids_are_distinct_from_approval_handles(self):
        adapter = FixtureHostedAdapter()
        original = adapter.correlations
        adapter.correlations = lambda: [{**item, "request_id": str(uuid4())} for item in original()]
        result = run_scenarios(
            adapter,
            source_revision="source-123",
            deployment_revision="deployment-456",
            environment="synthetic-hosted",
            target_kind="synthetic-nonproduction",
            target_id="synthetic-target",
        )
        self.assertEqual(result["scenarios"]["hosted_interruption"]["status"], "blocked")
        self.assertTrue(
            all(
                item["status"] == "passed"
                for name, item in result["scenarios"].items()
                if name != "hosted_interruption"
            )
        )

    def test_live_correlation_metadata_survives_and_invalid_status_is_rejected(self):
        adapter = FixtureHostedAdapter()
        original = adapter.correlations

        def correlations():
            return [
                {
                    **item,
                    "http_status": 403,
                    "hosted_phase": "resume",
                    "conversation_id": "synthetic-conversation",
                    "hosted_agent_name": "synthetic-agent",
                    "hosted_agent_version": "1",
                }
                for item in original()
            ]

        adapter.correlations = correlations
        args = {
            "source_revision": "source-123",
            "deployment_revision": "deployment-456",
            "environment": "synthetic-hosted",
            "target_kind": "synthetic-nonproduction",
            "target_id": "synthetic-target",
        }
        result = run_scenarios(adapter, **args)
        self.assertEqual(result["correlations"][0]["http_status"], 403)
        self.assertEqual(result["correlations"][0]["hosted_phase"], "resume")
        adapter.correlations = lambda: [{**correlations()[0], "http_status": True}]
        with self.assertRaisesRegex(ValueError, "HTTP status"):
            run_scenarios(adapter, **args)


if __name__ == "__main__":
    unittest.main()
