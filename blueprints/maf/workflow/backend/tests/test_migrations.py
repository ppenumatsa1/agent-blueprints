import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from psycopg import sql
from sqlalchemy import create_engine

from app.infrastructure.migrations import ROOT, SchemaDriftError
from app.store import PostgresStore
from tests.test_security import scoped_url


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ.get("MAF_TEST_DATABASE_URL")
        if not self.dsn:
            raise RuntimeError("MAF_TEST_DATABASE_URL must point to an isolated PostgreSQL test database.")
        self.schema = "migration_" + uuid4().hex
        with psycopg.connect(self.dsn) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.url = scoped_url(self.dsn, self.schema)
        self.store = PostgresStore(self.url)

    def drop_schema(self):
        with psycopg.connect(self.dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def rows(self):
        with self.store.connect() as connection:
            return tuple(
                tuple(connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall())
                for table in ("wf_cases", "wf_decisions", "wf_action_ledger", "wf_audit")
            )

    def seed_legacy(self):
        case_id = uuid4()
        with self.store.connect() as connection:
            connection.execute((ROOT / "baseline.sql").read_text(encoding="utf-8"))
            connection.execute(
                """INSERT INTO wf_cases (id,tenant_id,owner_id,reviewer_id,idempotency_key,
                   input_digest,payload,status,request_id,checkpoint_id,terminal_checkpoint_id,execution_complete)
                   VALUES (%s,'tenant','owner','reviewer','key','digest','{"value":42}',
                   'completed','request','checkpoint','terminal',true)""",
                (case_id,),
            )
            connection.execute(
                "INSERT INTO wf_decisions (case_id,decision,actor_id) VALUES (%s,'approved','reviewer')",
                (case_id,),
            )
            connection.execute("INSERT INTO wf_action_ledger (case_id,action_key) VALUES (%s,'effect')", (case_id,))
            connection.execute("INSERT INTO wf_audit (case_id,event,actor_id) VALUES (%s,'approved','reviewer')", (case_id,))

    def test_fresh_restart_and_concurrent_initialization(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: self.store.initialize(), range(2)))
        self.store.initialize()
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchall(), [{"version_num": "0001"}])
            self.assertEqual(connection.execute("SELECT count(*) AS n FROM wf_cases").fetchone()["n"], 0)

    def test_legacy_adoption_preserves_all_business_rows_and_restarts(self):
        self.seed_legacy()
        before = self.rows()
        self.store.initialize()
        self.store.initialize()
        self.assertEqual(self.rows(), before)
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"], "0001")

    def test_drift_fails_without_stamping_and_repair_recovers(self):
        self.seed_legacy()
        before = self.rows()
        with self.store.connect() as connection:
            connection.execute("ALTER TABLE wf_decisions DROP CONSTRAINT wf_decisions_decision_check")
        with self.assertRaises(SchemaDriftError):
            self.store.initialize()
        with self.store.connect() as connection:
            self.assertIsNone(connection.execute("SELECT to_regclass('alembic_version') AS v").fetchone()["v"])
            connection.execute(
                "ALTER TABLE wf_decisions ADD CONSTRAINT wf_decisions_decision_check CHECK (decision IN ('approved','rejected'))"
            )
        self.store.initialize()
        self.assertEqual(self.rows(), before)

    def test_drift_after_versioning_and_partial_baseline_are_rejected(self):
        self.store.initialize()
        with self.store.connect() as connection:
            connection.execute("ALTER TABLE wf_cases ADD COLUMN unexpected text")
        with self.assertRaises(SchemaDriftError):
            self.store.initialize()
        with self.store.connect() as connection:
            connection.execute("ALTER TABLE wf_cases DROP COLUMN unexpected")
        self.store.initialize()
        with self.store.connect() as connection:
            connection.execute("DROP TABLE wf_audit")
        with self.assertRaises(SchemaDriftError):
            self.store.initialize()

    def test_unknown_revision_is_not_rewritten(self):
        self.store.initialize()
        with self.store.connect() as connection:
            connection.execute("UPDATE alembic_version SET version_num = 'future'")
        with self.assertRaises(CommandError) as failure:
            self.store.initialize()
        self.assertIn("future", str(failure.exception))
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"], "future")

    def test_identity_sequence_drift_is_rejected(self):
        self.seed_legacy()
        with self.store.connect() as connection:
            connection.execute("ALTER SEQUENCE wf_audit_id_seq INCREMENT BY 2")
        with self.assertRaises(SchemaDriftError):
            self.store.initialize()
        with self.store.connect() as connection:
            connection.execute("ALTER SEQUENCE wf_audit_id_seq INCREMENT BY 1")
        self.store.initialize()

    def test_interrupted_upgrade_rolls_back_and_retry_succeeds(self):
        original_upgrade = command.upgrade

        def interrupted(*args, **kwargs):
            original_upgrade(*args, **kwargs)
            raise RuntimeError("simulated failure before commit")

        with patch("app.infrastructure.migrations.command.upgrade", side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                self.store.initialize()
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT to_regclass('wf_cases') AS cases, to_regclass('alembic_version') AS version"
            ).fetchone()
            self.assertEqual(row, {"cases": None, "version": None})
        self.store.initialize()

    def test_downgrade_refuses_and_preserves_rows_and_revision(self):
        self.seed_legacy()
        self.store.initialize()
        before = self.rows()
        engine = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(self.url))
        self.addCleanup(engine.dispose)
        with self.assertRaisesRegex(RuntimeError, "no safe automatic downgrade"):
            with engine.begin() as connection:
                config = Config()
                config.set_main_option("script_location", str(ROOT).replace("%", "%%"))
                config.attributes["connection"] = connection
                command.downgrade(config, "base")
        self.assertEqual(self.rows(), before)
        self.store.initialize()
