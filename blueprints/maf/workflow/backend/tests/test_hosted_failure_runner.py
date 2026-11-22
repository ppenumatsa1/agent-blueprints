import unittest
from dataclasses import replace
from uuid import uuid4

from tests.hosted_failure_runner import (
    AuthorizationFailure,
    HostedRecord,
    ReconciliationRequired,
    StaleApproval,
    TransientFailure,
    UnknownOutcome,
    run_scenarios,
)


class FixtureHostedAdapter:
    source_revision = "source-123"
    deployment_revision = "deployment-456"

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
    def test_all_required_hosted_failure_scenarios_are_explicit_and_pass(self):
        result = run_scenarios(
            FixtureHostedAdapter(),
            source_revision="source-123",
            deployment_revision="deployment-456",
            environment="synthetic-hosted",
        )
        self.assertEqual(len(result["scenarios"]), 9)
        self.assertEqual(
            {item["status"] for item in result["scenarios"].values()},
            {"passed"},
        )
        self.assertEqual(result["source_revision"], "source-123")
        self.assertEqual(result["deployment_revision"], "deployment-456")
        self.assertTrue(result["correlations"])

    def test_exact_active_revision_is_required(self):
        with self.assertRaisesRegex(ValueError, "source revision"):
            run_scenarios(
                FixtureHostedAdapter(),
                source_revision="different",
                deployment_revision="deployment-456",
                environment="synthetic-hosted",
            )
        with self.assertRaisesRegex(ValueError, "deployment revision"):
            run_scenarios(
                FixtureHostedAdapter(),
                source_revision="source-123",
                deployment_revision="different",
                environment="synthetic-hosted",
            )

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
            )


if __name__ == "__main__":
    unittest.main()
