import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from psycopg import sql
from sqlalchemy import create_engine

from app.infrastructure.migrations import ROOT, SchemaDriftError, upgrade, validate
from app.infrastructure.store import PostgresStore
from examples.synthetic_application import initialize as initialize_example
from tests.test_security import scoped_url


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ.get("MAF_TEST_DATABASE_URL")
        if not self.dsn:
            raise RuntimeError(
                "MAF_TEST_DATABASE_URL must point to an isolated PostgreSQL test database."
            )
        self.schema = "migration_" + uuid4().hex
        with psycopg.connect(self.dsn) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.url = scoped_url(self.dsn, self.schema)
        self.store = PostgresStore(self.url)

    def drop_schema(self):
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

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
            connection.execute(
                "INSERT INTO wf_action_ledger (case_id,action_key) VALUES (%s,'effect')", (case_id,)
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id,event,actor_id) VALUES (%s,'approved','reviewer')",
                (case_id,),
            )

    def test_fresh_restart_and_concurrent_initialization(self):
        with self.assertRaises(SchemaDriftError):
            self.store.initialize()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: upgrade(self.url), range(2)))
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: self.store.initialize(), range(2)))
        self.store.initialize()
        with self.store.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT version_num FROM alembic_version").fetchall(),
                [{"version_num": "0001"}],
            )
            self.assertEqual(
                connection.execute("SELECT count(*) AS n FROM wf_cases").fetchone()["n"], 0
            )

    def test_legacy_adoption_preserves_all_business_rows_and_restarts(self):
        self.seed_legacy()
        before = self.rows()
        with self.assertRaises(SchemaDriftError):
            self.store.initialize()
        original_stamp = command.stamp
        with patch("app.infrastructure.migrations.command.stamp", wraps=original_stamp) as stamp:
            upgrade(self.url)
        stamp.assert_called_once()
        self.assertEqual(stamp.call_args.args[1], "0001")
        self.store.initialize()
        self.assertEqual(self.rows(), before)
        with self.store.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[
                    "version_num"
                ],
                "0001",
            )

    def test_drift_fails_without_stamping_and_repair_recovers(self):
        self.seed_legacy()
        before = self.rows()
        with self.store.connect() as connection:
            connection.execute(
                "ALTER TABLE wf_decisions DROP CONSTRAINT wf_decisions_decision_check"
            )
        with self.assertRaises(SchemaDriftError):
            upgrade(self.url)
        with self.store.connect() as connection:
            self.assertIsNone(
                connection.execute("SELECT to_regclass('alembic_version') AS v").fetchone()["v"]
            )
            connection.execute(
                "ALTER TABLE wf_decisions ADD CONSTRAINT wf_decisions_decision_check CHECK (decision IN ('approved','rejected'))"
            )
        upgrade(self.url)
        self.assertEqual(self.rows(), before)

    def test_drift_after_versioning_and_partial_baseline_are_rejected(self):
        upgrade(self.url)
        with self.store.connect() as connection:
            connection.execute("ALTER TABLE wf_cases ADD COLUMN unexpected text")
        with self.assertRaises(SchemaDriftError):
            self.store.initialize()
        with self.store.connect() as connection:
            connection.execute("ALTER TABLE wf_cases DROP COLUMN unexpected")
        upgrade(self.url)
        with self.store.connect() as connection:
            connection.execute("DROP TABLE wf_audit")
        with self.assertRaises(SchemaDriftError):
            upgrade(self.url)

    def test_unknown_revision_is_not_rewritten(self):
        upgrade(self.url)
        with self.store.connect() as connection:
            connection.execute("UPDATE alembic_version SET version_num = 'future'")
        with self.assertRaises(CommandError) as failure:
            self.store.initialize()
        self.assertIn("future", str(failure.exception))
        with self.store.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[
                    "version_num"
                ],
                "future",
            )

    def test_second_revision_upgrades_fresh_and_existing_and_restarts(self):
        self.seed_legacy()
        upgrade(self.url)
        before = self.rows()
        fixture_dir = Path(__file__).with_name("migration_fixtures")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "migrations"
            shutil.copytree(ROOT, root)
            shutil.copy2(fixture_dir / "0002_add_marker.py", root / "versions")
            shutil.copy2(fixture_dir / "0002.json", root / "manifests")
            with self.assertRaises(SchemaDriftError):
                validate(self.url, root=root)
            with self.store.connect() as connection:
                connection.execute("CREATE TABLE wf_future_fixture (id integer PRIMARY KEY)")
            with self.assertRaisesRegex(SchemaDriftError, "owned by another revision"):
                upgrade(self.url, root=root)
            with self.store.connect() as connection:
                connection.execute("DROP TABLE wf_future_fixture")
            original_upgrade = command.upgrade

            def interrupted(*args, **kwargs):
                original_upgrade(*args, **kwargs)
                raise RuntimeError("failure before commit")

            with patch("app.infrastructure.migrations.command.upgrade", side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, "failure before commit"):
                    upgrade(self.url, root=root)
            self.store.initialize()
            self.assertEqual(self.rows(), before)
            upgrade(self.url, root=root)
            validate(self.url, root=root)
            with patch(
                "app.infrastructure.migrations.validate",
                side_effect=lambda dsn: validate(dsn, root=root),
            ):
                self.store.initialize()
            after = self.rows()
            self.assertEqual(
                tuple(
                    {k: v for k, v in row.items() if k != "migration_marker"} for row in after[0]
                ),
                before[0],
            )
            self.assertEqual(after[1:], before[1:])
            with self.store.connect() as connection:
                self.assertEqual(
                    connection.execute("SELECT version_num FROM alembic_version").fetchone()[
                        "version_num"
                    ],
                    "0002",
                )
                connection.execute("ALTER TABLE wf_cases ADD COLUMN drift text")
            with self.assertRaises(SchemaDriftError):
                validate(self.url, root=root)

            other = "migration_" + uuid4().hex
            with psycopg.connect(self.dsn) as connection:
                connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(other)))
            try:
                fresh = scoped_url(self.dsn, other)
                upgrade(fresh, root=root)
                validate(fresh, root=root)
                with psycopg.connect(fresh) as connection:
                    self.assertEqual(
                        connection.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                        "0002",
                    )
                    self.assertIsNone(
                        connection.execute("SELECT migration_marker FROM wf_cases").fetchone()
                    )
                    connection.execute("DROP TABLE alembic_version")
                with self.assertRaises(SchemaDriftError):
                    upgrade(fresh, root=root)
            finally:
                with psycopg.connect(self.dsn) as connection:
                    connection.execute(
                        sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(other))
                    )

    def test_runtime_validation_needs_no_schema_or_database_create(self):
        upgrade(self.url)
        role = "migration_reader_" + uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(self.schema), sql.Identifier(role)
                )
            )
            connection.execute(
                sql.SQL("GRANT SELECT ON {}.alembic_version TO {}").format(
                    sql.Identifier(self.schema), sql.Identifier(role)
                )
            )

        def cleanup_role():
            with psycopg.connect(self.dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

        self.addCleanup(cleanup_role)
        original_connect = psycopg.connect

        def read_only_connect(dsn):
            connection = original_connect(dsn, autocommit=True)
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            privileges = connection.execute(
                "SELECT has_database_privilege(current_user, current_database(), 'CREATE'), "
                "has_schema_privilege(current_user, current_schema(), 'CREATE')"
            ).fetchone()
            self.assertEqual(privileges, (False, False))
            connection.autocommit = False
            return connection

        with patch("app.infrastructure.migrations.psycopg.connect", side_effect=read_only_connect):
            self.store.initialize()

    def test_identity_sequence_drift_is_rejected(self):
        self.seed_legacy()
        with self.store.connect() as connection:
            connection.execute("ALTER SEQUENCE wf_audit_id_seq INCREMENT BY 2")
        with self.assertRaises(SchemaDriftError):
            upgrade(self.url)
        with self.store.connect() as connection:
            connection.execute("ALTER SEQUENCE wf_audit_id_seq INCREMENT BY 1")
        upgrade(self.url)

    def test_synthetic_example_requires_explicit_preparation(self):
        upgrade(self.url)
        with self.assertRaisesRegex(RuntimeError, "preparation step"):
            initialize_example(self.store)
        env = os.environ.copy()
        env["DATABASE_URL"] = self.url
        subprocess.run(
            [sys.executable, "-m", "examples.synthetic_application"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            check=True,
        )
        initialize_example(self.store)

    def test_tampered_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "migrations"
            shutil.copytree(ROOT, root)
            manifest = root / "manifests" / "0001.json"
            manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(SchemaDriftError, "manifest"):
                upgrade(self.url, root=root)
        with self.store.connect() as connection:
            self.assertIsNone(
                connection.execute("SELECT to_regclass('alembic_version') AS v").fetchone()["v"]
            )

    def test_interrupted_upgrade_rolls_back_and_retry_succeeds(self):
        original_upgrade = command.upgrade

        def interrupted(*args, **kwargs):
            original_upgrade(*args, **kwargs)
            raise RuntimeError("simulated failure before commit")

        with patch("app.infrastructure.migrations.command.upgrade", side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                upgrade(self.url)
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT to_regclass('wf_cases') AS cases, to_regclass('alembic_version') AS version"
            ).fetchone()
            self.assertEqual(row, {"cases": None, "version": None})
        upgrade(self.url)

    def test_downgrade_refuses_and_preserves_rows_and_revision(self):
        self.seed_legacy()
        upgrade(self.url)
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
