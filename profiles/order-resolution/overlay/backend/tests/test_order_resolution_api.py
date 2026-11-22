import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.composition import create_app
from app.config import Settings
from app.infrastructure.identity import EntraIdentity
from app.domain.errors import ActionError
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.application import build_application
from app.order_resolution.effects import EffectIdentity
from app.order_resolution.host import OrderResolutionWorkflowHost
from app.order_resolution.migrations import upgrade
from app.order_resolution.persistence import (
    OrderResolutionStore,
    PostgresSyntheticDestination,
)
from app.order_resolution.workflow import build_order_resolution_workflow
from tests.test_security import API, OWNER, REVIEWER, TENANT, TokenFixture, scoped_url


def payload(order_id: str, amount: str, delay_days: int, evidence: list[dict]) -> dict:
    return {
        "order": {
            "id": order_id,
            "amount": amount,
            "currency": "USD",
            "issue": "late_delivery",
            "delay_days": delay_days,
        },
        "policy_evidence": evidence,
    }


def late_policy() -> dict:
    return {
        "policy": "POLICY-LATE@1",
        "current": True,
        "applicable": True,
        "digest_valid": True,
    }


class OrderResolutionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("MAF_TEST_DATABASE_URL")
        if not cls.dsn:
            raise RuntimeError(
                "MAF_TEST_DATABASE_URL must point to an isolated PostgreSQL test database."
            )
        cls.tokens = TokenFixture()

    def setUp(self):
        self.schema = "order_resolution_" + uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self._drop_schema)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(
            TENANT,
            API,
            scoped_url(self.dsn, self.schema),
            Path(self.temp.name) / "checkpoints",
        )
        upgrade(self.settings.database_url)
        self.store = OrderResolutionStore(self.settings.database_url)
        self.identity = EntraIdentity(self.settings, self.tokens.client())
        self.owner_token = self.tokens.token(subject=OWNER)
        self.reviewer_token = self.tokens.token(
            subject=REVIEWER,
            scopes="workflow.read workflow.approve",
            roles=["Workflow.Approver"],
        )

    def _drop_schema(self):
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def client(self):
        return TestClient(
            create_app(
                self.settings,
                build_application(),
                store=self.store,
                identity=self.identity,
            )
        )

    @staticmethod
    def headers(token: str, key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        if key is not None:
            headers["Idempotency-Key"] = key
        return headers

    def submit(self, client: TestClient, body: dict) -> dict:
        response = client.post(
            "/api/cases",
            headers=self.headers(self.owner_token, str(uuid4())),
            json={"reviewer_id": REVIEWER, "payload": body},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def decision_body(record: dict, decision: str) -> dict:
        proposal = record["payload"]["proposal"]
        return {
            "decision": decision,
            "proposal_version": proposal["version"],
            "action": proposal["action"],
            "destination_id": proposal["destination_id"],
            "handle": record["decision_handle"],
            "channel": "api",
        }

    def database_counts(self, case_id: UUID) -> dict[str, int]:
        with self.store.connect() as connection:
            return {
                "actions": connection.execute(
                    "SELECT count(*) AS count FROM order_resolution_actions WHERE case_id = %s",
                    (case_id,),
                ).fetchone()["count"],
                "claims": connection.execute(
                    "SELECT count(*) AS count FROM wf_action_ledger WHERE case_id = %s",
                    (case_id,),
                ).fetchone()["count"],
                "decisions": connection.execute(
                    "SELECT count(*) AS count FROM wf_decisions WHERE case_id = %s",
                    (case_id,),
                ).fetchone()["count"],
                "failures": connection.execute(
                    """
                    SELECT count(*) AS count FROM wf_audit
                    WHERE case_id = %s AND event = 'resolution_failed'
                    """,
                    (case_id,),
                ).fetchone()["count"],
            }

    def durability_counts(self, case_id: UUID) -> dict[str, int]:
        with self.store.connect() as connection:
            return {
                "proposal_decisions": connection.execute(
                    "SELECT count(*) AS count FROM order_resolution_decisions WHERE case_id = %s",
                    (case_id,),
                ).fetchone()["count"],
                "effect_claims": connection.execute(
                    "SELECT count(*) AS count FROM order_resolution_effects WHERE case_id = %s",
                    (case_id,),
                ).fetchone()["count"],
                "synthetic_effects": connection.execute(
                    """
                    SELECT count(*) AS count
                    FROM order_resolution_synthetic_effects s
                    JOIN order_resolution_effects e ON e.effect_key = s.effect_key
                    WHERE e.case_id = %s
                    """,
                    (case_id,),
                ).fetchone()["count"],
                "denials": connection.execute(
                    """
                    SELECT count(*) AS count FROM order_resolution_audit
                    WHERE case_id = %s AND event = 'decision_denied'
                    """,
                    (case_id,),
                ).fetchone()["count"],
            }

    def crash_worker(self, mode: str, pending: dict) -> subprocess.CompletedProcess:
        proposal = pending["payload"]["proposal"]
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.order_resolution_crash_worker",
                mode,
                self.settings.database_url,
                str(self.settings.checkpoint_root),
                pending["id"],
                str(proposal["version"]),
                proposal["action"],
                proposal["destination_id"],
                pending["decision_handle"],
            ],
            cwd=Path(__file__).resolve().parents[1],
            timeout=30,
            check=False,
        )

    def action(self, case_id: UUID):
        with self.store.connect() as connection:
            return connection.execute(
                """
                SELECT proposal_version, order_id, action, destination_id,
                    effect_key, amount::text, currency
                FROM order_resolution_actions WHERE case_id = %s
                """,
                (case_id,),
            ).fetchone()

    def test_ors_001_auto_refund_runs_through_api_maf_and_postgres(self):
        with self.client() as client:
            record = self.submit(client, payload("ORDER-LOW", "79.00", 4, [late_policy()]))

        case_id = UUID(record["id"])
        stored = self.store.get(case_id)
        self.assertEqual((record["status"], record["execution_complete"]), ("completed", True))
        self.assertIsNone(stored.decision)
        self.assertTrue(stored.terminal_checkpoint_id)
        self.assertIsNone(stored.checkpoint_id)
        self.assertEqual(
            dict(self.action(case_id)),
            {
                "proposal_version": 1,
                "order_id": "ORDER-LOW",
                "action": "partial_refund_10",
                "destination_id": "synthetic-refund",
                "effect_key": EffectIdentity.from_proposal(
                    self.store.get_current_proposal(str(case_id))
                ).key,
                "amount": "7.90",
                "currency": "USD",
            },
        )
        self.assertEqual(
            self.database_counts(case_id),
            {"actions": 1, "claims": 1, "decisions": 0, "failures": 0},
        )
        checkpoints = list((self.settings.checkpoint_root / str(case_id)).glob("*.json"))
        self.assertTrue(checkpoints)

    def test_concurrent_duplicate_requests_reuse_one_case_and_effect(self):
        body = payload("ORDER-DUPLICATE", "79.00", 4, [late_policy()])
        key = str(uuid4())

        def submit_duplicate(_: int):
            with self.client() as client:
                return client.post(
                    "/api/cases",
                    headers=self.headers(self.owner_token, key),
                    json={"reviewer_id": REVIEWER, "payload": body},
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit_duplicate, range(2)))

        self.assertEqual([response.status_code for response in responses], [200, 200])
        records = [response.json() for response in responses]
        self.assertEqual(len({record["id"] for record in records}), 1)
        case_id = UUID(records[0]["id"])
        self.assertTrue(all(record["status"] in {"created", "completed"} for record in records))
        self.assertEqual(self.store.get(case_id).status, "completed")
        self.assertEqual(self.database_counts(case_id)["actions"], 1)
        self.assertEqual(self.durability_counts(case_id)["effect_claims"], 1)
        self.assertEqual(self.durability_counts(case_id)["synthetic_effects"], 1)
        with self.store.connect() as connection:
            count = connection.execute(
                "SELECT count(*) AS count FROM order_resolution_requests WHERE case_id = %s",
                (case_id,),
            ).fetchone()["count"]
        self.assertEqual(count, 1)

    def test_ors_002_approval_pauses_before_usd_18_50_refund(self):
        with self.client() as client:
            pending = self.submit(client, payload("ORDER-HIGH", "185.00", 5, [late_policy()]))
            case_id = UUID(pending["id"])
            paused = self.store.get(case_id)
            self.assertEqual((pending["status"], pending["execution_complete"]), ("pending", False))
            self.assertTrue(paused.checkpoint_id)
            self.assertTrue(paused.request_id)
            self.assertIsNone(self.action(case_id))
            self.assertEqual(self.database_counts(case_id)["claims"], 0)
            checkpoint = (
                self.settings.checkpoint_root / str(case_id) / f"{paused.checkpoint_id}.json"
            )
            self.assertTrue(checkpoint.is_file())

            response = client.post(
                f"/api/cases/{case_id}/decision",
                headers=self.headers(self.reviewer_token),
                json=self.decision_body(pending, "approved"),
            )
            self.assertEqual(response.status_code, 200, response.text)
            completed = response.json()

        stored = self.store.get(case_id)
        self.assertEqual(
            (
                completed["status"],
                completed["decision"],
                completed["execution_complete"],
            ),
            ("completed", "approved", True),
        )
        self.assertTrue(stored.terminal_checkpoint_id)
        self.assertEqual(
            dict(self.action(case_id)),
            {
                "proposal_version": 1,
                "order_id": "ORDER-HIGH",
                "action": "partial_refund_10",
                "destination_id": "synthetic-refund",
                "effect_key": EffectIdentity.from_proposal(
                    self.store.get_current_proposal(str(case_id))
                ).key,
                "amount": "18.50",
                "currency": "USD",
            },
        )
        self.assertEqual(
            self.database_counts(case_id),
            {"actions": 1, "claims": 1, "decisions": 1, "failures": 0},
        )

    def test_ors_006_missing_policy_evidence_persists_failed_closed(self):
        with self.client() as client:
            record = self.submit(client, payload("ORDER-LOW", "79.00", 4, []))

        case_id = UUID(record["id"])
        stored = self.store.get(case_id)
        self.assertEqual(
            (
                record["status"],
                record["execution_complete"],
                record["failure_code"],
            ),
            ("failed", True, "policy_evidence_missing"),
        )
        self.assertIsNone(record["payload"]["proposal"])
        self.assertEqual(record["payload"]["resolution_failure"], "policy_evidence_missing")
        self.assertIsNone(stored.checkpoint_id)
        self.assertIsNone(stored.terminal_checkpoint_id)
        self.assertFalse((self.settings.checkpoint_root / str(case_id)).exists())
        self.assertEqual(
            self.database_counts(case_id),
            {"actions": 0, "claims": 0, "decisions": 0, "failures": 1},
        )

    def test_decision_process_death_before_and_after_persistence_recovers_safely(self):
        for mode, return_code, persisted in (
            ("before-decision", 81, 0),
            ("after-decision", 82, 1),
        ):
            with self.subTest(mode=mode):
                with self.client() as client:
                    pending = self.submit(
                        client,
                        payload("ORDER-HIGH", "185.00", 5, [late_policy()]),
                    )
                case_id = UUID(pending["id"])
                self.assertEqual(self.crash_worker(mode, pending).returncode, return_code)
                self.assertEqual(
                    self.durability_counts(case_id)["proposal_decisions"],
                    persisted,
                )
                self.assertEqual(self.durability_counts(case_id)["synthetic_effects"], 0)

                if mode == "before-decision":
                    with self.client() as client:
                        response = client.post(
                            f"/api/cases/{case_id}/decision",
                            headers=self.headers(self.reviewer_token),
                            json=self.decision_body(pending, "approved"),
                        )
                        self.assertEqual(response.status_code, 200, response.text)
                else:
                    with self.client() as client:
                        response = client.get(
                            f"/api/cases/{case_id}",
                            headers=self.headers(self.owner_token),
                        )
                        self.assertEqual(response.status_code, 200, response.text)

                completed = self.store.get(case_id)
                self.assertEqual(
                    (completed.status, completed.decision, completed.execution_complete),
                    ("completed", "approved", True),
                )
                self.assertEqual(
                    self.durability_counts(case_id),
                    {
                        "proposal_decisions": 1,
                        "effect_claims": 1,
                        "synthetic_effects": 1,
                        "denials": 0,
                    },
                )

    def test_effect_process_death_before_and_after_send_reconciles_once(self):
        for mode, return_code, effects_after_crash in (
            ("before-effect", 83, 0),
            ("after-effect", 84, 1),
        ):
            with self.subTest(mode=mode):
                with self.client() as client:
                    pending = self.submit(
                        client,
                        payload("ORDER-HIGH", "185.00", 5, [late_policy()]),
                    )
                case_id = UUID(pending["id"])
                self.assertEqual(
                    self.crash_worker("after-decision", pending).returncode,
                    82,
                )
                self.assertEqual(self.crash_worker(mode, pending).returncode, return_code)
                self.assertEqual(
                    self.durability_counts(case_id)["synthetic_effects"],
                    effects_after_crash,
                )
                self.assertIsNone(self.action(case_id))

                with self.client() as client:
                    response = client.get(
                        f"/api/cases/{case_id}",
                        headers=self.headers(self.owner_token),
                    )
                    self.assertEqual(response.status_code, 200, response.text)

                completed = self.store.get(case_id)
                self.assertTrue(completed.execution_complete)
                self.assertEqual(self.durability_counts(case_id)["synthetic_effects"], 1)
                self.assertEqual(self.durability_counts(case_id)["effect_claims"], 1)
                self.assertIsNotNone(self.action(case_id))

    def test_timeout_after_send_is_unknown_then_authoritatively_reconciled(self):
        with self.client() as client:
            pending = self.submit(
                client,
                payload("ORDER-HIGH", "185.00", 5, [late_policy()]),
            )
        case_id = UUID(pending["id"])
        self.assertEqual(self.crash_worker("after-decision", pending).returncode, 82)

        destination = PostgresSyntheticDestination(self.store)
        destination.timeout_after_send_once = True
        host = OrderResolutionWorkflowHost(
            self.store,
            RecordOrderResolutionAction(self.store, destination),
            self.settings.checkpoint_root,
            build_order_resolution_workflow,
        )
        with self.assertRaises(ActionError):
            asyncio.run(host.resume(case_id))
        self.assertEqual(self.durability_counts(case_id)["synthetic_effects"], 1)
        with self.store.connect() as connection:
            status = connection.execute(
                "SELECT status FROM order_resolution_effects WHERE case_id = %s",
                (case_id,),
            ).fetchone()["status"]
        self.assertEqual(status, "unknown")

        asyncio.run(host.resume(case_id))
        self.assertEqual(self.durability_counts(case_id)["synthetic_effects"], 1)
        self.assertEqual(self.store.get(case_id).status, "completed")
        self.assertEqual(len(destination.timeouts), 3)
        self.assertTrue(all(0 < value <= 5.0 for value in destination.timeouts))

    def test_unauthorized_stale_conflicting_and_concurrent_decisions_fail_closed(self):
        with self.client() as client:
            pending = self.submit(
                client,
                payload("ORDER-HIGH", "185.00", 5, [late_policy()]),
            )
            case_id = UUID(pending["id"])
            stranger = self.tokens.token(
                subject=str(uuid4()),
                scopes="workflow.read workflow.approve",
                roles=["Workflow.Approver"],
            )
            denied = client.post(
                f"/api/cases/{case_id}/decision",
                headers=self.headers(stranger),
                json=self.decision_body(pending, "approved"),
            )
            self.assertEqual(denied.status_code, 403)
            stale = self.decision_body(pending, "approved")
            stale["proposal_version"] = 2
            denied = client.post(
                f"/api/cases/{case_id}/decision",
                headers=self.headers(self.reviewer_token),
                json=stale,
            )
            self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.durability_counts(case_id)["denials"], 2)
        self.assertEqual(self.durability_counts(case_id)["synthetic_effects"], 0)

        def decide(value):
            with self.client() as client:
                return client.post(
                    f"/api/cases/{case_id}/decision",
                    headers=self.headers(self.reviewer_token),
                    json=self.decision_body(pending, value),
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(decide, ("approved", "rejected")))
        self.assertEqual(sorted(statuses), [200, 409])
        final = self.store.get(case_id)
        self.assertIn(final.status, ("completed", "rejected"))
        self.assertEqual(
            self.durability_counts(case_id)["synthetic_effects"],
            int(final.status == "completed"),
        )


if __name__ == "__main__":
    unittest.main()
