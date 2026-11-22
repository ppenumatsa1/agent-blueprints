import asyncio
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

from app.domain.errors import AccessDenied, ActionError, CheckpointError, Conflict
from app.domain.models import Principal
from app.domain.policy import CaseAccessPolicy, JsonObjectRules
from app.infrastructure.store import PostgresStore
from app.usecases.service import WorkflowService
from app.workflows.host import LocalWorkflowHost
from app.workflows.workflow import create_workflow
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


class WorkflowIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("MAF_TEST_DATABASE_URL")
        if not dsn:
            raise RuntimeError("MAF_TEST_DATABASE_URL must point to an isolated PostgreSQL test database.")
        cls.store = PostgresStore(dsn)
        cls.store.initialize()
        initialize_fixture(cls.store)

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
        stranger = Principal(
            "test-tenant", "stranger", REVIEWER.scopes, REVIEWER.roles
        )
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
        self.assertEqual((failed.status, failed.decision, failed.failure_code), ("failed", "approved", "action_failed"))
        self.assertEqual(action_count(self.store, case.id), 0)
        self.host.action = FixtureAction()
        await self.host.resume(case.id)
        self.assertEqual(self.store.get(case.id).status, "completed")
        self.assertEqual(action_count(self.store, case.id), 1)

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

    def _worker(self, operation, case_id, barrier=None, marker=None):
        command = [
            sys.executable, "-m", "tests.crash_worker", operation,
            str(case_id), str(self.checkpoint_root),
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

    def _restart_worker(self, case_id):
        worker = self._worker("resume", case_id)
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

    async def test_worker_crash_after_decision_before_resume(self):
        await self._crash_and_recover("after-decision")

    async def test_worker_crash_after_action_before_checkpoint(self):
        await self._crash_and_recover("after-action")


if __name__ == "__main__":
    unittest.main()
