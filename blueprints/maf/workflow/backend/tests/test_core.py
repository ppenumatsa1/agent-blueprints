import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agent_framework import FileCheckpointStorage

from app.domain.errors import AccessDenied, ActionError, CheckpointError, Conflict, InvalidInput
from app.domain.models import Principal
from app.domain.policy import CaseAccessPolicy, JsonObjectRules
from app.infrastructure.migrations import upgrade
from app.infrastructure.store import PostgresStore
from app.usecases.service import WorkflowService
from app.workflows.host import LocalWorkflowHost
from app.workflows.workflow import create_workflow
from examples.synthetic_application import build_application, prepare
from tests.fixture_application import FixtureAction, action_count, initialize_fixture


OWNER = Principal(
    "test-tenant", "owner-1", frozenset({"workflow.read", "workflow.write"}), frozenset()
)
REVIEWER = Principal(
    "test-tenant",
    "reviewer-1",
    frozenset({"workflow.read", "workflow.approve"}),
    frozenset({"Workflow.Approver"}),
)


def synthetic_action_count(store, case_id):
    with store.connect() as connection:
        row = connection.execute(
            "SELECT count(*) AS count FROM synthetic_effects WHERE case_id = %s",
            (case_id,),
        ).fetchone()
    return row["count"]


class WorkflowIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("MAF_TEST_DATABASE_URL")
        if not dsn:
            raise RuntimeError(
                "MAF_TEST_DATABASE_URL must point to an isolated PostgreSQL test database."
            )
        cls.store = PostgresStore(dsn)
        upgrade(dsn)
        cls.store.initialize()
        initialize_fixture(cls.store)
        prepare(cls.store)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.checkpoint_root = Path(self.temp.name) / "checkpoints"
        self.host = LocalWorkflowHost(self.store, FixtureAction(), self.checkpoint_root)
        self.service = WorkflowService(self.store, self.host, JsonObjectRules(), CaseAccessPolicy())

    async def submit(self, payload=None, key=None, reviewer="reviewer-1"):
        return await self.service.submit(
            OWNER, reviewer, payload if payload is not None else {"value": 42}, key or str(uuid4())
        )

    def use_synthetic_application(self):
        application = build_application()
        self.host = LocalWorkflowHost(
            self.store,
            application.action,
            self.checkpoint_root,
            workflow_factory=application.workflow_factory,
        )
        self.service = WorkflowService(self.store, self.host, application.rules, application.policy)
        return application

    def fixed_checkpoint_timestamps(self):
        save = FileCheckpointStorage.save

        async def save_at_same_time(storage, checkpoint):
            checkpoint.timestamp = "2026-01-01T00:00:00+00:00"
            return await save(storage, checkpoint)

        return patch.object(FileCheckpointStorage, "save", save_at_same_time)

    def ordered_checkpoints(self, key):
        checkpoints = self.host._checkpoints

        async def ordered(storage):
            return sorted(await checkpoints(storage), key=key)

        return patch.object(self.host, "_checkpoints", ordered)

    async def test_native_pause_approval_and_replay_are_idempotent(self):
        case = await self.submit()
        self.assertEqual(case.status, "pending")
        self.assertTrue(case.request_id)
        self.assertTrue(case.checkpoint_id)
        self.assertEqual(action_count(self.store, case.id), 0)
        completed = await self.service.decide(REVIEWER, case.id, "approved")
        self.assertEqual(completed.status, "completed")
        self.assertTrue(completed.execution_complete)
        self.assertEqual(action_count(self.store, case.id), 1)
        replayed = await self.service.decide(REVIEWER, case.id, "approved")
        self.assertEqual(replayed.status, "completed")
        self.assertEqual(action_count(self.store, case.id), 1)

    async def test_action_requires_a_persisted_matching_decision(self):
        case = await self.submit()
        with self.assertRaises(Conflict):
            self.store.apply_once(case.id, True, FixtureAction())
        with self.assertRaises(Conflict):
            self.store.apply_once(case.id, False, FixtureAction())
        self.assertEqual(action_count(self.store, case.id), 0)

    async def test_rejection_and_unauthorized_decisions_never_apply_action(self):
        case = await self.submit()
        stranger = Principal("test-tenant", "stranger", REVIEWER.scopes, REVIEWER.roles)
        for actor in (
            stranger,
            Principal("other-tenant", REVIEWER.subject, REVIEWER.scopes, REVIEWER.roles),
            Principal(REVIEWER.tenant_id, REVIEWER.subject, REVIEWER.scopes, frozenset()),
            Principal(REVIEWER.tenant_id, REVIEWER.subject, frozenset(), REVIEWER.roles),
            OWNER,
        ):
            with self.subTest(actor=actor):
                with self.assertRaises(AccessDenied):
                    await self.service.decide(actor, case.id, "approved")
        self.assertIsNone(self.store.get(case.id).decision)
        await self.host.resume(case.id)
        self.assertEqual(action_count(self.store, case.id), 0)
        rejected = await self.service.decide(REVIEWER, case.id, "rejected")
        self.assertEqual(rejected.status, "rejected")
        self.assertTrue(rejected.execution_complete)
        self.assertEqual(action_count(self.store, case.id), 0)
        with self.assertRaises(Conflict):
            await self.service.decide(REVIEWER, case.id, "approved")

    async def test_record_access_and_decisions_are_case_scoped(self):
        first = await self.submit()
        second = await self.submit(reviewer="reviewer-2")
        with self.assertRaises(AccessDenied):
            self.service.read(REVIEWER, second.id)
        with self.assertRaises(AccessDenied):
            await self.service.decide(REVIEWER, second.id, "approved")
        self.assertEqual(self.service.read(REVIEWER, first.id).id, first.id)
        self.assertEqual(self.store.get(second.id).status, "pending")
        self.assertEqual(action_count(self.store, second.id), 0)
        self.assertNotEqual(first.checkpoint_id, second.checkpoint_id)
        self.assertNotEqual(first.request_id, second.request_id)

    async def test_history_filters_authorized_records_before_pagination(self):
        tenant = f"history-tenant-{uuid4()}"
        owner_id = f"history-owner-{uuid4()}"
        reviewer_id = f"history-reviewer-{uuid4()}"
        other_tenant = f"history-tenant-{uuid4()}"
        owner = Principal(tenant, owner_id, frozenset({"workflow.read"}), frozenset())
        reviewer = Principal(tenant, reviewer_id, frozenset({"workflow.read"}), frozenset())
        stranger = Principal(tenant, f"history-stranger-{uuid4()}", owner.scopes, frozenset())
        second_owner = Principal(tenant, f"history-owner-{uuid4()}", owner.scopes, frozenset())
        tenant_owner = Principal(other_tenant, owner_id, owner.scopes, frozenset())
        other_reviewer_id = f"history-reviewer-{uuid4()}"

        own_first = self.store.create(
            owner, other_reviewer_id, {"private": "PAYLOAD-CANARY"}, str(uuid4()), "digest"
        )
        own_second = self.store.create(
            owner, other_reviewer_id, {"private": "PAYLOAD-CANARY"}, str(uuid4()), "digest"
        )
        assigned = self.store.create(second_owner, reviewer_id, {"value": 1}, str(uuid4()), "digest")
        hidden = self.store.create(
            Principal(tenant, f"hidden-owner-{uuid4()}", owner.scopes, frozenset()),
            f"hidden-reviewer-{uuid4()}",
            {"value": 2},
            str(uuid4()),
            "digest",
        )
        other_tenant_case = self.store.create(
            tenant_owner, f"other-reviewer-{uuid4()}", {"value": 3}, str(uuid4()), "digest"
        )
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE wf_cases SET created_at = now() + interval '1 day' WHERE id = %s",
                (hidden.id,),
            )
            connection.execute(
                "UPDATE wf_cases SET status = 'pending' WHERE id = %s", (own_first.id,)
            )
            connection.execute(
                "UPDATE wf_cases SET status = 'completed' WHERE id = %s", (own_second.id,)
            )

        first_page = self.service.history(owner, status=None, cursor=None, limit=1)
        self.assertEqual(len(first_page.items), 1)
        self.assertEqual(first_page.items[0].id, own_second.id)
        self.assertIsNotNone(first_page.next_cursor)
        second_page = self.service.history(
            owner, status=None, cursor=first_page.next_cursor, limit=1
        )
        self.assertEqual([item.id for item in second_page.items], [own_first.id])
        self.assertIsNone(second_page.next_cursor)
        self.assertEqual(
            [item.id for item in self.service.history(
                reviewer, status=None, cursor=None, limit=10
            ).items],
            [assigned.id],
        )
        self.assertEqual(
            [item.id for item in self.service.history(
                tenant_owner, status=None, cursor=None, limit=10
            ).items],
            [other_tenant_case.id],
        )
        self.assertEqual(
            self.service.history(stranger, status=None, cursor=None, limit=10).items, ()
        )
        self.assertEqual(
            [item.id for item in self.service.history(
                owner, status="pending", cursor=None, limit=10
            ).items],
            [own_first.id],
        )
        with self.assertRaises(AccessDenied):
            self.service.history(
                Principal(tenant, owner_id, frozenset(), frozenset()),
                status=None,
                cursor=None,
                limit=10,
            )

    async def test_history_cursor_order_is_stable_and_status_bound(self):
        tenant = f"history-tenant-{uuid4()}"
        owner = Principal(tenant, f"history-owner-{uuid4()}", frozenset({"workflow.read"}), frozenset())
        ids = [
            self.store.create(owner, f"reviewer-{index}", {"value": index}, str(uuid4()), "digest").id
            for index in range(3)
        ]
        fixed_time = "2026-01-01T00:00:00+00:00"
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE wf_cases SET created_at = %s WHERE id = ANY(%s)",
                (fixed_time, ids),
            )

        page = self.service.history(owner, status=None, cursor=None, limit=1)
        repeated = self.service.history(owner, status=None, cursor=None, limit=1)
        next_page = self.service.history(
            owner, status=None, cursor=page.next_cursor, limit=1
        )
        self.assertEqual(page.items, repeated.items)
        self.assertNotEqual(page.items[0].id, next_page.items[0].id)
        self.assertEqual(len({page.items[0].id, next_page.items[0].id}), 2)
        with self.assertRaises(InvalidInput):
            self.service.history(owner, status="pending", cursor=page.next_cursor, limit=1)
        oversized_activity_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "version": 1,
                    "kind": "activity",
                    "created_at": fixed_time,
                    "id": str(2**63),
                    "status": None,
                },
                separators=(",", ":"),
            ).encode()
        ).decode().rstrip("=")
        with self.assertRaises(InvalidInput):
            self.service.activity(owner, ids[0], cursor=oversized_activity_cursor, limit=1)

    async def test_activity_maps_allowlisted_audit_events_without_private_fields(self):
        tenant = f"activity-tenant-{uuid4()}"
        owner = Principal(tenant, f"activity-owner-{uuid4()}", frozenset({"workflow.read"}), frozenset())
        reviewer = f"activity-reviewer-{uuid4()}"
        case = self.store.create(owner, reviewer, {"private": "PAYLOAD-CANARY"}, str(uuid4()), "digest")
        with self.store.connect() as connection:
            connection.execute(
                """
                UPDATE wf_cases SET request_id = 'REQUEST-CANARY',
                    checkpoint_id = 'CHECKPOINT-CANARY',
                    terminal_checkpoint_id = 'TERMINAL-CANARY'
                WHERE id = %s
                """,
                (case.id,),
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event, actor_id) VALUES (%s, %s, %s)",
                (case.id, "decision_recorded", "ACTOR-CANARY"),
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event, actor_id) VALUES (%s, %s, %s)",
                (case.id, "workflow_finished", "ACTOR-CANARY"),
            )
            for event in (
                "hosted_request_saved",
                "automatic_action_applied",
                "hosted_workflow_finished",
                "resolution_failed",
            ):
                connection.execute(
                    "INSERT INTO wf_audit (case_id, event, actor_id) VALUES (%s, %s, %s)",
                    (case.id, event, "ACTOR-CANARY"),
                )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event, actor_id) VALUES (%s, %s, %s)",
                (case.id, "private-event-CANARY", "PRIVATE-EVENT-CONTENT-CANARY"),
            )

        first_page = self.service.activity(owner, case.id, cursor=None, limit=1)
        repeated = self.service.activity(owner, case.id, cursor=None, limit=1)
        remaining = self.service.activity(
            owner, case.id, cursor=first_page.next_cursor, limit=20
        )
        self.assertEqual(first_page.items, repeated.items)
        self.assertEqual(first_page.items[0].event_type, "workflow_failed")
        events = [item.event_type for item in first_page.items + remaining.items]
        self.assertEqual(
            set(events),
            {
                "created",
                "request_recorded",
                "decision_recorded",
                "action_applied",
                "workflow_finished",
                "workflow_failed",
            },
        )
        self.assertNotIn("private-event-CANARY", repr(first_page) + repr(remaining))
        self.assertNotIn("ACTOR-CANARY", repr(first_page) + repr(remaining))
        self.assertNotIn("CHECKPOINT-CANARY", repr(first_page) + repr(remaining))
        self.assertNotIn("REQUEST-CANARY", repr(first_page) + repr(remaining))
        self.assertNotIn("PAYLOAD-CANARY", repr(first_page) + repr(remaining))

    async def test_submission_idempotency_rejects_changed_payload(self):
        key = str(uuid4())
        first = await self.submit({"value": 42}, key)
        same = await self.submit({"value": 42}, key)
        self.assertEqual(first.id, same.id)
        with self.assertRaises(Conflict):
            await self.submit({"value": 43}, key)
        with self.assertRaises(Conflict):
            await self.submit({"value": 42}, key, reviewer="reviewer-2")

    async def test_case_lock_rejects_a_second_worker(self):
        case = await self.submit()
        with self.store.run_lock(case.id):
            with self.assertRaises(Conflict):
                with self.store.run_lock(case.id):
                    self.fail("A concurrent worker acquired the same case lock.")

    async def test_concurrent_conflicting_decisions_do_not_repeat_action(self):
        case = await self.submit()
        results = await asyncio.gather(
            self.service.decide(REVIEWER, case.id, "approved"),
            self.service.decide(REVIEWER, case.id, "rejected"),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, Conflict) for result in results), 1)
        final = self.store.get(case.id)
        self.assertIn(final.status, ("completed", "rejected"))
        self.assertEqual(action_count(self.store, case.id), int(final.status == "completed"))

    async def test_action_failure_is_visible_and_transaction_rolls_back(self):
        self.host.action = FixtureAction(fail=True)
        case = await self.submit()
        with self.assertRaises(ActionError):
            await self.service.decide(REVIEWER, case.id, "approved")
        failed = self.store.get(case.id)
        self.assertEqual(
            (failed.status, failed.decision, failed.failure_code),
            ("failed", "approved", "action_failed"),
        )
        self.assertEqual(action_count(self.store, case.id), 0)
        self.host.action = FixtureAction()
        await self.host.resume(case.id)
        self.assertEqual(self.store.get(case.id).status, "completed")
        self.assertEqual(action_count(self.store, case.id), 1)

    async def test_application_owned_workflow_approves_rejects_and_restarts(self):
        self.use_synthetic_application()

        approved = await self.submit(key=f"synthetic-approve-{uuid4()}")
        self.assertEqual(approved.status, "pending")
        self.use_synthetic_application()
        await self.host.resume(approved.id)
        completed = await self.service.decide(REVIEWER, approved.id, "approved")
        self.assertEqual(completed.status, "completed")
        self.assertTrue(completed.execution_complete)
        self.assertEqual(synthetic_action_count(self.store, approved.id), 1)

        rejected = await self.submit(key=f"synthetic-reject-{uuid4()}")
        self.use_synthetic_application()
        await self.host.resume(rejected.id)
        denied = await self.service.decide(REVIEWER, rejected.id, "rejected")
        self.assertEqual(denied.status, "rejected")
        self.assertTrue(denied.execution_complete)
        self.assertEqual(synthetic_action_count(self.store, rejected.id), 0)

    async def test_missing_checkpoint_fails_closed(self):
        case = await self.submit()
        (self.checkpoint_root / str(case.id) / f"{case.checkpoint_id}.json").unlink()
        with self.assertRaises(CheckpointError):
            await self.service.decide(REVIEWER, case.id, "approved")
        self.assertEqual(self.store.get(case.id).decision, "approved")
        self.assertEqual(action_count(self.store, case.id), 0)

    async def test_corrupt_checkpoint_fails_closed(self):
        case = await self.submit()
        path = self.checkpoint_root / str(case.id) / f"{case.checkpoint_id}.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaises(CheckpointError):
            await self.service.decide(REVIEWER, case.id, "approved")
        self.assertEqual(action_count(self.store, case.id), 0)

    async def test_pending_checkpoint_reconciles_when_database_pointer_was_not_saved(self):
        case = self.store.create(OWNER, "reviewer-1", {"value": 1}, str(uuid4()), "digest")
        storage = self.host._storage(case.id)
        workflow = create_workflow(self.store, FixtureAction(), storage)
        requests = []
        async for event in workflow.run({"case_id": str(case.id)}, stream=True):
            if event.type == "request_info":
                requests.append(event.request_id)
        self.assertEqual(self.store.get(case.id).status, "created")
        await self.host.start(case.id)
        recovered = self.store.get(case.id)
        self.assertEqual(recovered.status, "pending")
        self.assertEqual(recovered.request_id, requests[0])

    async def test_equal_checkpoint_timestamps_select_current_pause_and_terminal(self):
        with self.fixed_checkpoint_timestamps():
            with self.ordered_checkpoints(lambda item: item.iteration_count):
                case = await self.submit()
                completed = await self.service.decide(REVIEWER, case.id, "approved")
            stored = await self.host._checkpoints(self.host._storage(case.id))

        terminal = next(
            item for item in stored if item.checkpoint_id == completed.terminal_checkpoint_id
        )
        self.assertFalse(terminal.pending_request_info_events)
        self.assertFalse(any(terminal.messages.values()))
        self.assertGreater(terminal.iteration_count, 1)
        self.assertEqual(action_count(self.store, case.id), 1)
        await self.host.resume(case.id)
        self.assertEqual(action_count(self.store, case.id), 1)

    async def test_recovery_selects_pending_checkpoint_when_timestamps_tie(self):
        case = self.store.create(OWNER, "reviewer-1", {"value": 1}, str(uuid4()), "digest")
        storage = self.host._storage(case.id)
        workflow = create_workflow(self.store, FixtureAction(), storage)
        with self.fixed_checkpoint_timestamps():
            requests = await self.host._requests(
                workflow.run({"case_id": str(case.id)}, stream=True), case.id
            )
            with self.ordered_checkpoints(lambda item: item.iteration_count):
                await self.host.start(case.id)

        recovered = self.store.get(case.id)
        self.assertEqual(recovered.status, "pending")
        self.assertEqual(recovered.request_id, requests[0])

    async def test_terminal_checkpoint_is_not_an_earlier_tied_checkpoint(self):
        with self.fixed_checkpoint_timestamps():
            with self.ordered_checkpoints(lambda item: not item.pending_request_info_events):
                case = await self.submit()
            with self.ordered_checkpoints(lambda item: item.iteration_count):
                completed = await self.service.decide(REVIEWER, case.id, "approved")
            stored = await self.host._checkpoints(self.host._storage(case.id))

        terminal = next(
            item for item in stored if item.checkpoint_id == completed.terminal_checkpoint_id
        )
        self.assertFalse(terminal.pending_request_info_events)
        self.assertFalse(any(terminal.messages.values()))
        self.assertGreater(terminal.iteration_count, 1)
        self.assertEqual(action_count(self.store, case.id), 1)

    async def test_completed_workflow_rejects_nonterminal_checkpoint_on_replay(self):
        case = await self.submit()
        completed = await self.service.decide(REVIEWER, case.id, "approved")
        checkpoints = await self.host._checkpoints(self.host._storage(case.id))
        entry = min(checkpoints, key=lambda item: item.iteration_count)
        self.assertNotEqual(entry.checkpoint_id, completed.terminal_checkpoint_id)
        self.assertNotEqual(entry.checkpoint_id, case.checkpoint_id)

        for checkpoint_id in (entry.checkpoint_id, case.checkpoint_id):
            with self.subTest(checkpoint_id=checkpoint_id):
                with self.store.connect() as connection:
                    connection.execute(
                        "UPDATE wf_cases SET terminal_checkpoint_id = %s WHERE id = %s",
                        (checkpoint_id, case.id),
                    )
                with self.assertRaises(CheckpointError):
                    await self.host.resume(case.id)
                self.assertEqual(action_count(self.store, case.id), 1)

    async def test_failed_terminal_checkpoint_stays_recoverable(self):
        case = await self.submit()
        save = FileCheckpointStorage.save

        async def fail_terminal_save(storage, checkpoint):
            if checkpoint.iteration_count > 1:
                raise OSError("Synthetic checkpoint write failure")
            return await save(storage, checkpoint)

        with patch.object(FileCheckpointStorage, "save", fail_terminal_save):
            with self.assertRaises(CheckpointError):
                await self.service.decide(REVIEWER, case.id, "approved")

        self.assertFalse(self.store.get(case.id).execution_complete)
        self.assertEqual(action_count(self.store, case.id), 1)
        await self.host.resume(case.id)
        self.assertTrue(self.store.get(case.id).execution_complete)
        self.assertEqual(action_count(self.store, case.id), 1)

    def _worker(self, operation, case_id, barrier=None, marker=None, application="fixture"):
        command = [
            sys.executable,
            "-m",
            "tests.crash_worker",
            operation,
            str(case_id),
            str(self.checkpoint_root),
            "--application",
            application,
        ]
        if barrier:
            command.extend(["--barrier", barrier, "--marker", str(marker)])
        return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def _wait_for_marker(self, process, marker):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not marker.exists():
            if process.poll() is not None:
                out, err = process.communicate()
                self.fail(f"Worker exited before the crash barrier: {out} {err}")
            time.sleep(0.05)
        self.assertTrue(marker.exists(), "Worker did not reach the crash barrier.")

    def _restart_worker(self, case_id, application="fixture"):
        worker = self._worker("resume", case_id, application=application)
        out, err = worker.communicate(timeout=30)
        self.assertEqual(worker.returncode, 0, f"Recovery worker failed: {out} {err}")

    async def _crash_and_recover(self, barrier):
        case = await self.submit()
        marker = Path(self.temp.name) / "barrier"
        worker = self._worker("decide", case.id, barrier, marker)
        try:
            self._wait_for_marker(worker, marker)
            before = self.store.get(case.id)
            self.assertEqual(before.decision, "approved")
            self.assertFalse(before.execution_complete)
            self.assertEqual(action_count(self.store, case.id), int(barrier == "after-action"))
        finally:
            worker.kill()
            worker.communicate(timeout=10)
        self._restart_worker(case.id)
        recovered = self.store.get(case.id)
        self.assertEqual(recovered.status, "completed")
        self.assertTrue(recovered.execution_complete)
        self.assertEqual(action_count(self.store, case.id), 1)
        self._restart_worker(case.id)
        self.assertEqual(action_count(self.store, case.id), 1)

    async def _crash_and_recover_synthetic(self, barrier):
        self.use_synthetic_application()
        case = await self.submit(key=f"synthetic-crash-{barrier}-{uuid4()}")
        marker = Path(self.temp.name) / f"synthetic-{barrier}"
        worker = self._worker("decide", case.id, barrier, marker, "synthetic")
        try:
            self._wait_for_marker(worker, marker)
            before = self.store.get(case.id)
            self.assertEqual(before.decision, "approved")
            self.assertFalse(before.execution_complete)
            self.assertEqual(
                synthetic_action_count(self.store, case.id), int(barrier == "after-action")
            )
        finally:
            worker.kill()
            worker.communicate(timeout=10)
        self._restart_worker(case.id, "synthetic")
        recovered = self.store.get(case.id)
        self.assertEqual(recovered.status, "completed")
        self.assertTrue(recovered.execution_complete)
        self.assertEqual(synthetic_action_count(self.store, case.id), 1)
        self._restart_worker(case.id, "synthetic")
        self.assertEqual(synthetic_action_count(self.store, case.id), 1)

    async def test_worker_crash_after_decision_before_resume(self):
        await self._crash_and_recover("after-decision")

    async def test_worker_crash_after_action_before_checkpoint(self):
        await self._crash_and_recover("after-action")

    async def test_application_owned_workflow_recovers_after_decision_crash(self):
        await self._crash_and_recover_synthetic("after-decision")

    async def test_application_owned_workflow_recovers_after_action_crash(self):
        await self._crash_and_recover_synthetic("after-action")


if __name__ == "__main__":
    unittest.main()
