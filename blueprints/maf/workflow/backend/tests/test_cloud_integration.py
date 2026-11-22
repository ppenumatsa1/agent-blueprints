import json
import unittest
from dataclasses import replace
from unittest.mock import ANY, patch
from uuid import uuid4

from app.config import Settings
from app.domain.errors import CheckpointError, HostedWorkflowError
from app.domain.models import Case
from app.infrastructure.database import (
    BoundedConnectionPool,
    DatabaseConnectionOptions,
    DatabaseConnector,
    POSTGRES_TOKEN_SCOPE,
)
from app.infrastructure.hosted import (
    HostedResult,
    HostedStart,
    HttpHostedWorkflowClient,
)
from app.workflows.hosted import HostedWorkflowHost


TENANT = "10000000-0000-4000-8000-000000000001"
API = "20000000-0000-4000-8000-000000000002"
API_IDENTITY = "30000000-0000-4000-8000-000000000003"
OWNER = "40000000-0000-4000-8000-000000000004"
REVIEWER = "50000000-0000-4000-8000-000000000005"


class StaticTokenProvider:
    def __init__(self, value: str = "api-managed-identity-token"):
        self.value = value
        self.scopes = []

    def get_token(self, scope: str) -> str:
        self.scopes.append(scope)
        return self.value


class Response:
    def __init__(self, value: dict):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit: int) -> bytes:
        return json.dumps(self.value).encode("utf-8")


class FakeStore:
    def __init__(self, *, approval_required: bool = True):
        self.case = Case(
            id=uuid4(),
            tenant_id=TENANT,
            owner_id=OWNER,
            reviewer_id=REVIEWER,
            payload={"proposal": {"approval_required": approval_required}},
            status="created",
            decision=None,
            request_id=None,
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=False,
            failure_code=None,
        )
        self.action_count = 0
        self.start_claims = 0
        self.resume_claims = 0

    def run_lock(self, _case_id):
        class Lock:
            def __enter__(self):
                return None

            def __exit__(self, *_):
                return False

        return Lock()

    def get(self, _case_id):
        return self.case

    def claim_hosted_start(self, _case_id, operation_id):
        self.start_claims += 1
        self.case = replace(
            self.case,
            status="pending",
            checkpoint_id=operation_id,
            request_id=operation_id,
            failure_code="hosted_outcome_unknown",
        )

    def confirm_hosted_pending(
        self, _case_id, operation_id, execution_id, request_id
    ):
        if (
            self.case.checkpoint_id != operation_id
            or self.case.request_id != operation_id
        ):
            raise AssertionError("The dispatch was not claimed before confirmation.")
        self.case = replace(
            self.case,
            checkpoint_id=execution_id,
            request_id=request_id,
            failure_code=None,
        )

    def record_decision(self, decision: str):
        self.case = replace(self.case, status=decision, decision=decision)

    def decision_actor(self, _case_id):
        return REVIEWER

    def claim_hosted_resume(self, _case_id):
        self.resume_claims += 1
        self.case = replace(self.case, failure_code="hosted_outcome_unknown")

    def apply_once(self, _case_id, approved, _action):
        if approved:
            self.action_count += 1

    def apply_automatic(self, _case_id, _action):
        self.action_count += 1
        self.case = replace(self.case, status="completed")

    def finish(self, _case_id, execution_id):
        self.case = replace(
            self.case,
            status="completed" if self.case.decision == "approved" else "rejected",
            execution_complete=True,
            terminal_checkpoint_id=execution_id,
            failure_code=None,
        )

    def finish_automatic(self, _case_id, execution_id):
        self.case = replace(
            self.case,
            execution_complete=True,
            terminal_checkpoint_id=execution_id,
            failure_code=None,
        )


class FakeHostedClient:
    def __init__(self, start_result=None, resume_result=None, status_result=None):
        self.start_result = start_result
        self.resume_result = resume_result
        self.status_result = status_result
        self.starts = []
        self.resumes = []
        self.statuses = []

    async def start(self, request):
        self.starts.append(request)
        if isinstance(self.start_result, Exception):
            raise self.start_result
        return self.start_result

    async def resume(self, request):
        self.resumes.append(request)
        if isinstance(self.resume_result, Exception):
            raise self.resume_result
        return self.resume_result

    async def status(self, operation_id):
        self.statuses.append(operation_id)
        if isinstance(self.status_result, Exception):
            raise self.status_result
        return self.status_result


class CloudConfigurationTests(unittest.TestCase):
    def test_hosted_mode_is_explicit_and_requires_tls_and_managed_identity(self):
        settings = Settings(
            TENANT,
            API,
            "postgresql://runtime@database.postgres.database.azure.com/app"
            "?sslmode=verify-full",
            None,
            host_mode="hosted",
            hosted_workflow_endpoint="https://agent.example.test/workflows",
            hosted_workflow_scope="api://hosted-agent/.default",
            api_managed_identity_client_id=API_IDENTITY,
            database_auth_mode="managed-identity",
            database_tls_mode="verify-full",
        )
        self.assertEqual(settings.host_mode, "hosted")
        self.assertIsNone(settings.checkpoint_root)
        self.assertNotIn("password", repr(settings))
        with self.assertRaises(ValueError):
            replace(settings, database_tls_mode="require")
        with self.assertRaises(ValueError):
            replace(settings, database_auth_mode="managed-identity", database_password="secret")
        with self.assertRaises(ValueError):
            replace(settings, hosted_workflow_endpoint="http://agent.example.test")

    def test_managed_identity_database_token_is_separate_and_tls_verified(self):
        provider = StaticTokenProvider("database-managed-identity-token")
        connector = DatabaseConnector(
            DatabaseConnectionOptions(
                "postgresql://runtime@database.postgres.database.azure.com/app",
                "managed-identity",
                None,
                API_IDENTITY,
                "verify-full",
            ),
            provider,
        )
        with patch("app.infrastructure.database.psycopg.connect") as connect:
            connector.connect()
        self.assertEqual(provider.scopes, [POSTGRES_TOKEN_SCOPE])
        connect.assert_called_once_with(
            "postgresql://runtime@database.postgres.database.azure.com/app",
            row_factory=ANY,
            sslmode="verify-full",
            password="database-managed-identity-token",
        )

    def test_postgres_pool_has_a_hard_borrower_bound(self):
        class Connection:
            closed = False

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                self.closed = True

        pool = BoundedConnectionPool(
            Connection,
            min_size=0,
            max_size=1,
            timeout_seconds=0.01,
            max_lifetime_seconds=60,
        )
        with pool.connection():
            with self.assertRaisesRegex(TimeoutError, "pool is exhausted"):
                with pool.connection():
                    self.fail("A second borrower exceeded the configured pool maximum.")
        pool.close()


class HostedClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_hosted_call_uses_api_identity_and_never_forwards_a_user_token(self):
        provider = StaticTokenProvider()
        captured = {}

        def open_request(request, timeout):
            captured["authorization"] = request.headers["Authorization"]
            captured["idempotency"] = request.get_header("Idempotency-key")
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return Response(
                {
                    "operation_id": captured["body"]["operation_id"],
                    "execution_id": "hosted-execution",
                    "status": "pending",
                    "request_id": "hosted-request",
                }
            )

        client = HttpHostedWorkflowClient(
            "https://agent.example.test",
            "api://hosted-agent/.default",
            provider,
        )
        with patch("app.infrastructure.hosted.urlopen", open_request):
            result = await client.start(
                HostedStart(
                    "case:one:start",
                    "case-one",
                    TENANT,
                    OWNER,
                    REVIEWER,
                    {"proposal": {"approval_required": True}},
                )
            )

        self.assertEqual(result.status, "pending")
        self.assertEqual(provider.scopes, ["api://hosted-agent/.default"])
        self.assertEqual(captured["authorization"], "Bearer api-managed-identity-token")
        self.assertNotIn("access_token", captured["body"])
        self.assertNotIn("authorization", captured["body"])

    async def test_hosted_transport_failure_is_visible_and_not_success_shaped(self):
        client = HttpHostedWorkflowClient(
            "https://agent.example.test",
            "api://hosted-agent/.default",
            StaticTokenProvider(),
        )
        with patch(
            "app.infrastructure.hosted.urlopen",
            side_effect=TimeoutError("lost acknowledgment"),
        ):
            with self.assertRaisesRegex(HostedWorkflowError, "outcome is unknown"):
                await client.status("case:one:start")


class HostedWorkflowHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_claims_before_send_and_binds_opaque_hosted_correlation(self):
        store = FakeStore()
        operation = f"case:{store.case.id}:start"
        client = FakeHostedClient(
            start_result=HostedResult(
                operation,
                "hosted-execution",
                "pending",
                "opaque-request",
            )
        )
        host = HostedWorkflowHost(store, object(), client)
        await host.start(store.case.id)
        self.assertEqual(store.start_claims, 1)
        self.assertEqual(
            (store.case.status, store.case.checkpoint_id, store.case.request_id),
            ("pending", "hosted-execution", "opaque-request"),
        )
        self.assertEqual(client.starts[0].owner_id, OWNER)
        self.assertFalse(hasattr(client.starts[0], "access_token"))

    async def test_unknown_start_is_reconciled_without_replaying_dispatch(self):
        store = FakeStore(approval_required=False)
        operation = f"case:{store.case.id}:start"
        client = FakeHostedClient(
            start_result=HostedWorkflowError("unknown"),
            status_result=HostedResult(operation, "hosted-terminal", "automatic"),
        )
        host = HostedWorkflowHost(store, object(), client)
        with self.assertRaises(HostedWorkflowError):
            await host.start(store.case.id)
        await host.start(store.case.id)
        self.assertEqual(len(client.starts), 1)
        self.assertEqual(client.statuses, [operation])
        self.assertTrue(store.case.execution_complete)
        self.assertEqual(store.action_count, 1)

    async def test_approval_resume_is_idempotent_and_conflicting_outcome_fails_closed(self):
        store = FakeStore()
        operation = f"case:{store.case.id}:start"
        store.claim_hosted_start(store.case.id, operation)
        store.confirm_hosted_pending(
            store.case.id, operation, "hosted-execution", "opaque-request"
        )
        store.record_decision("approved")
        resume_operation = f"case:{store.case.id}:decision:approved"
        client = FakeHostedClient(
            resume_result=HostedResult(
                resume_operation,
                "hosted-terminal",
                "approved",
            )
        )
        host = HostedWorkflowHost(store, object(), client)
        await host.resume(store.case.id)
        await host.resume(store.case.id)
        self.assertEqual(len(client.resumes), 1)
        self.assertEqual(store.action_count, 1)
        self.assertEqual(client.resumes[0].reviewer_id, REVIEWER)

        conflicting = FakeStore()
        operation = f"case:{conflicting.case.id}:start"
        conflicting.claim_hosted_start(conflicting.case.id, operation)
        conflicting.confirm_hosted_pending(
            conflicting.case.id, operation, "hosted-execution", "opaque-request"
        )
        conflicting.record_decision("approved")
        bad_operation = f"case:{conflicting.case.id}:decision:approved"
        bad_client = FakeHostedClient(
            resume_result=HostedResult(bad_operation, "hosted-terminal", "rejected")
        )
        with self.assertRaises(CheckpointError):
            await HostedWorkflowHost(conflicting, object(), bad_client).resume(
                conflicting.case.id
            )
        self.assertEqual(conflicting.action_count, 0)


if __name__ == "__main__":
    unittest.main()
