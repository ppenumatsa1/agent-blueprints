import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from app.domain.errors import ActionError, AccessDenied, Conflict
from app.infrastructure.migrations import upgrade
from app.infrastructure.store import PostgresStore
from app.usecases.service import WorkflowService
from app.domain.policy import CaseAccessPolicy, JsonObjectRules
from app.workflows.host import LocalWorkflowHost
from examples.external_effect_boundary import EffectRequest, ExternalEffectAction, Observation
from tests.test_core import OWNER, REVIEWER


class FixtureAuthorizer:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.operation = "fixture-v1"
        self.destination_id = "fixture"
        self.return_value = True

    def authorize(self, connection, case, request):
        decision = connection.execute(
            "SELECT decision, actor_id FROM wf_decisions WHERE case_id = %s", (case.id,)
        ).fetchone()
        expected = {
            "case_id": str(case.id),
            "tenant_id": OWNER.tenant_id,
            "owner_id": OWNER.subject,
            "reviewer_id": REVIEWER.subject,
            "operation": self.operation,
            "destination_id": self.destination_id,
            "payload": {"value": 42},
        }
        if (
            not self.allowed
            or case.decision != "approved"
            or not decision
            or decision["decision"] != "approved"
            or decision["actor_id"] != case.reviewer_id
            or case.owner_id == case.reviewer_id
            or request.key != f"case:{case.id}:action"
            or json.loads(request.body) != expected
            or hashlib.sha256(request.body).hexdigest() != request.digest
        ):
            raise AccessDenied("Effect not authorized.")
        return self.return_value


class DurableDestination:
    """Separate SQLite database represents a downstream with atomic key binding."""

    def __init__(self, path):
        self.path = path
        self.fault = None
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS bindings "
                "(key TEXT PRIMARY KEY, digest TEXT NOT NULL, body BLOB NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS effects "
                "(key TEXT PRIMARY KEY REFERENCES bindings(key), value TEXT NOT NULL)"
            )

    def observe(self, request):
        if self.fault == "unknown":
            return Observation.UNKNOWN
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute(
                "SELECT b.digest, b.body, e.value FROM bindings b "
                "LEFT JOIN effects e ON e.key = b.key WHERE b.key = ?",
                (request.key,),
            ).fetchone()
            orphan = db.execute("SELECT 1 FROM effects WHERE key = ?", (request.key,)).fetchone()
        if row is None:
            return Observation.UNKNOWN if orphan else Observation.ABSENT
        if row[0] != request.digest or row[1] != request.body:
            return Observation.CONFLICT
        if row[2] is None or hashlib.sha256(row[1]).hexdigest() != row[0]:
            return Observation.UNKNOWN
        expected = json.dumps(json.loads(row[1])["payload"], sort_keys=True)
        return Observation.APPLIED if row[2] == expected else Observation.UNKNOWN

    def send(self, request):
        if self.fault == "before-effect":
            raise RuntimeError("Failure before effect.")
        if hashlib.sha256(request.body).hexdigest() != request.digest:
            raise RuntimeError("Request digest does not match the body.")
        effect = json.dumps(json.loads(request.body)["payload"], sort_keys=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute(
                "INSERT OR IGNORE INTO bindings VALUES (?, ?, ?)",
                (request.key, request.digest, request.body),
            )
            stored = db.execute(
                "SELECT digest, body FROM bindings WHERE key = ?", (request.key,)
            ).fetchone()
            if stored != (request.digest, request.body):
                raise RuntimeError("Conflicting request.")
            if self.fault == "between-binding-and-effect":
                raise RuntimeError("Transaction interrupted.")
            db.execute("INSERT OR IGNORE INTO effects VALUES (?, ?)", (request.key, effect))
            stored_effect = db.execute(
                "SELECT value FROM effects WHERE key = ?", (request.key,)
            ).fetchone()[0]
            if stored_effect != effect:
                raise RuntimeError("Conflicting effect.")
        if self.fault == "after-effect":
            raise RuntimeError("Acknowledgment lost.")

    def count(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute("SELECT count(*) FROM effects").fetchone()[0]


class ExternalEffectTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("MAF_TEST_DATABASE_URL")
        if not dsn:
            raise RuntimeError("MAF_TEST_DATABASE_URL must point to an isolated test database.")
        cls.store = PostgresStore(dsn)
        upgrade(dsn)
        cls.store.initialize()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.destination = DurableDestination(root / "downstream.sqlite")
        self.authorizer = FixtureAuthorizer()
        self.action = ExternalEffectAction(
            self.authorizer, self.destination, operation="fixture-v1", destination_id="fixture"
        )
        self.host = LocalWorkflowHost(self.store, self.action, root / "checkpoints")
        self.service = WorkflowService(self.store, self.host, JsonObjectRules(), CaseAccessPolicy())

    async def submit(self):
        return await self.service.submit(OWNER, REVIEWER.subject, {"value": 42}, str(uuid4()))

    async def test_rejection_and_unauthorized_decisions_never_send(self):
        case = await self.submit()
        stranger = type(REVIEWER)(REVIEWER.tenant_id, "stranger", REVIEWER.scopes, REVIEWER.roles)
        with self.assertRaises(AccessDenied):
            await self.service.decide(stranger, case.id, "approved")
        await self.service.decide(REVIEWER, case.id, "rejected")
        self.assertEqual(self.destination.count(), 0)
        with self.assertRaises(Conflict):
            await self.service.decide(REVIEWER, case.id, "approved")

    async def test_effect_authorization_is_required_even_after_approval(self):
        case = await self.submit()
        self.authorizer.allowed = False
        with self.assertRaises(ActionError):
            await self.service.decide(REVIEWER, case.id, "approved")
        self.assertEqual(self.destination.count(), 0)
        self.authorizer.allowed = True
        await self.host.resume(case.id)
        self.assertEqual(self.destination.count(), 1)

    async def test_nonaffirmative_authorizer_result_fails_closed(self):
        case = await self.submit()
        self.authorizer.return_value = False
        with self.assertRaises(ActionError):
            await self.service.decide(REVIEWER, case.id, "approved")
        self.assertEqual(self.destination.count(), 0)
        self.assertFalse(self.store.get(case.id).execution_complete)

    async def test_unauthorized_request_fields_are_rejected_before_first_effect(self):
        for field in ("operation", "destination", "payload"):
            with self.subTest(field=field):
                case = await self.submit()
                before = self.destination.count()
                self.host.action = ExternalEffectAction(
                    self.authorizer,
                    self.destination,
                    operation="unapproved" if field == "operation" else "fixture-v1",
                    destination_id="unapproved" if field == "destination" else "fixture",
                )
                if field == "payload":
                    with self.store.connect() as connection:
                        connection.execute(
                            "UPDATE wf_cases SET payload = %s::jsonb WHERE id = %s",
                            ('{"value":43}', case.id),
                        )
                with self.assertRaises(ActionError):
                    await self.service.decide(REVIEWER, case.id, "approved")
                self.assertEqual(self.destination.count(), before)
                self.assertFalse(self.store.get(case.id).execution_complete)
                if field == "payload":
                    with self.store.connect() as connection:
                        connection.execute(
                            "UPDATE wf_cases SET payload = %s::jsonb WHERE id = %s",
                            ('{"value":42}', case.id),
                        )
                self.host.action = self.action
                await self.host.resume(case.id)
                self.assertEqual(self.destination.count(), before + 1)

    async def test_fault_windows_retry_with_one_effect(self):
        for fault in ("before-effect", "between-binding-and-effect", "after-effect", "after-ack"):
            with self.subTest(fault=fault):
                case = await self.submit()
                before = self.destination.count()
                self.destination.fault = fault
                if fault == "after-ack":
                    real_action = self.action

                    class FailAfterAck:
                        def apply(self, connection, case):
                            real_action.apply(connection, case)
                            raise RuntimeError("Local commit lost after acknowledgment.")

                    self.host.action = FailAfterAck()
                with self.assertRaises(ActionError):
                    await self.service.decide(REVIEWER, case.id, "approved")
                self.assertEqual(
                    self.destination.count(), before + int(fault in ("after-effect", "after-ack"))
                )
                if fault == "between-binding-and-effect":
                    with closing(sqlite3.connect(self.destination.path)) as db:
                        self.assertIsNone(
                            db.execute(
                                "SELECT 1 FROM bindings WHERE key = ?",
                                (f"case:{case.id}:action",),
                            ).fetchone()
                        )
                self.destination.fault = None
                self.host.action = self.action
                await self.host.resume(case.id)
                await self.host.resume(case.id)
                self.assertTrue(self.store.get(case.id).execution_complete)
                self.assertEqual(self.destination.count(), before + 1)

    async def test_unknown_and_conflicting_binding_fail_closed(self):
        case = await self.submit()
        self.destination.fault = "unknown"
        with self.assertRaises(ActionError):
            await self.service.decide(REVIEWER, case.id, "approved")
        self.assertEqual(self.destination.count(), 0)
        self.destination.fault = None
        with closing(sqlite3.connect(self.destination.path)) as db, db:
            db.execute(
                "INSERT INTO bindings VALUES (?, ?, ?)",
                (f"case:{case.id}:action", "different", b"conflict"),
            )
        with self.assertRaises(ActionError):
            await self.host.resume(case.id)
        self.assertEqual(self.destination.count(), 0)
        self.assertFalse(self.store.get(case.id).execution_complete)

    async def test_ambiguous_effect_stays_blocked_until_reconciled_and_authorized(self):
        case = await self.submit()
        self.destination.fault = "after-effect"
        with self.assertRaises(ActionError):
            await self.service.decide(REVIEWER, case.id, "approved")
        self.destination.fault = "unknown"
        with self.assertRaises(ActionError):
            await self.host.resume(case.id)
        self.assertEqual(self.destination.count(), 1)
        self.authorizer.allowed = False
        self.destination.fault = None
        with self.assertRaises(ActionError):
            await self.host.resume(case.id)
        self.assertFalse(self.store.get(case.id).execution_complete)
        self.authorizer.allowed = True
        await self.host.resume(case.id)
        self.assertEqual(self.destination.count(), 1)
        self.assertTrue(self.store.get(case.id).execution_complete)

    async def test_changed_operation_cannot_reuse_an_effect_key(self):
        case = await self.submit()
        self.destination.fault = "after-effect"
        with self.assertRaises(ActionError):
            await self.service.decide(REVIEWER, case.id, "approved")
        self.destination.fault = None
        self.authorizer.operation = "different"
        self.host.action = ExternalEffectAction(
            self.authorizer, self.destination, operation="different", destination_id="fixture"
        )
        with self.assertRaises(ActionError):
            await self.host.resume(case.id)
        self.assertEqual(self.destination.count(), 1)
        self.authorizer.operation = "fixture-v1"
        self.host.action = self.action
        await self.host.resume(case.id)
        self.assertTrue(self.store.get(case.id).execution_complete)

    async def test_downstream_atomic_key_binding_under_concurrent_sends(self):
        body = b'{"payload":{"value":42}}'
        request = EffectRequest("shared", hashlib.sha256(body).hexdigest(), body)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self.destination.send, request) for _ in range(8)]
            for future in futures:
                future.result()
        self.assertEqual(self.destination.count(), 1)
        with self.assertRaises(RuntimeError):
            self.destination.send(EffectRequest("shared", "forged", body))
        changed = b'{"payload":{"value":43}}'
        with self.assertRaises(RuntimeError):
            self.destination.send(
                EffectRequest("shared", hashlib.sha256(changed).hexdigest(), changed)
            )
        self.assertEqual(self.destination.count(), 1)

    async def test_concurrent_retries_and_conflicting_decisions(self):
        case = await self.submit()
        self.store.record_decision(case.id, REVIEWER, "approved")
        with self.assertRaises(Conflict):
            self.store.record_decision(case.id, REVIEWER, "rejected")
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(self.store.apply_once, case.id, True, self.action) for _ in range(8)
            ]
            for future in futures:
                future.result()
        self.assertEqual(self.destination.count(), 1)
        await self.host.resume(case.id)
        self.assertTrue(self.store.get(case.id).execution_complete)

    async def test_concurrent_approval_and_rejection_choose_one_outcome(self):
        case = await self.submit()
        results = await asyncio.gather(
            self.service.decide(REVIEWER, case.id, "approved"),
            self.service.decide(REVIEWER, case.id, "rejected"),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, Conflict) for result in results), 1)
        final = self.store.get(case.id)
        self.assertIn(final.status, ("completed", "rejected"))
        self.assertEqual(self.destination.count(), int(final.status == "completed"))

    async def test_process_death_after_effect_and_acknowledgment(self):
        for barrier in ("after-effect", "after-ack"):
            with self.subTest(barrier=barrier):
                case = await self.submit()
                self.store.record_decision(case.id, REVIEWER, "approved")
                marker = Path(self.temp.name) / f"{barrier}.marker"
                worker = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "tests.external_effect_worker",
                        str(case.id),
                        str(self.destination.path),
                        str(marker),
                        barrier,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                try:
                    deadline = time.monotonic() + 30
                    while not marker.exists() and time.monotonic() < deadline:
                        if worker.poll() is not None:
                            out, err = worker.communicate()
                            self.fail(f"Worker exited before barrier: {out} {err}")
                        time.sleep(0.05)
                    self.assertTrue(marker.exists(), "Worker did not reach crash barrier.")
                finally:
                    worker.kill()
                    worker.communicate(timeout=10)
                before = self.destination.count()
                await self.host.resume(case.id)
                self.assertEqual(self.destination.count(), before)
                self.assertTrue(self.store.get(case.id).execution_complete)


if __name__ == "__main__":
    unittest.main()
