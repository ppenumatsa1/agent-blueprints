import os
import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.composition import create_app
from app.config import Settings
from app.infrastructure.identity import EntraIdentity
from app.infrastructure.migrations import upgrade
from app.order_resolution.application import build_application
from app.order_resolution.persistence import OrderResolutionStore
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

    def action(self, case_id: UUID):
        with self.store.connect() as connection:
            return connection.execute(
                """
                SELECT proposal_version, order_id, action, amount::text, currency
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
                json={"decision": "approved"},
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


if __name__ == "__main__":
    unittest.main()
