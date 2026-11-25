import asyncio
import hashlib
import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.errors import InsufficientPrivilege

from app.domain.errors import AccessDenied, Conflict
from app.domain.models import Principal
from app.domain.policy import CaseAccessPolicy
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.durability import Decision, DecisionCommand
from app.order_resolution.migrations import upgrade
from app.order_resolution.persistence import HOSTED_CHANNEL, OrderResolutionStore
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.service import OrderResolutionService


TENANT = str(uuid4())
OPERATOR = str(uuid4())
IDENTITY = str(uuid4())
ACTOR = Principal(
    TENANT,
    OPERATOR,
    frozenset({"workflow.read", "workflow.write", "workflow.approve"}),
    frozenset({"Acceptance.Operator", "Workflow.Approver"}),
)
PAYLOAD = {
    "order": {
        "id": "ORDER-POC-FIXTURE",
        "amount": "185.00",
        "currency": "USD",
        "issue": "late_delivery",
        "delay_days": 5,
    },
    "policy_evidence": [
        {
            "policy": "POLICY-LATE@1",
            "current": True,
            "applicable": True,
            "digest_valid": True,
        }
    ],
}


class PocDatabaseBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("MAF_TEST_DATABASE_URL")
        if not source:
            raise RuntimeError("The POC boundary tests require isolated MAF_TEST_DATABASE_URL.")
        name = f"ors_poc_{uuid4().hex}"
        runtime = f"{name}_api"
        password = uuid4().hex
        cls.admin_dsn = make_conninfo(source, dbname=name)
        cls.runtime_dsn = make_conninfo(cls.admin_dsn, user=runtime, password=password)
        with psycopg.connect(source, autocommit=True) as connection:
            if not connection.execute(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            ).fetchone()[0]:
                raise unittest.SkipTest(
                    "The disposable Azure role-mapping fixture needs a superuser."
                )
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(runtime), sql.Literal(password)
                )
            )
            cls.addClassCleanup(
                cls.execute_admin,
                source,
                sql.SQL("DROP ROLE {}").format(sql.Identifier(runtime)),
            )
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            cls.addClassCleanup(
                cls.execute_admin,
                source,
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)),
            )
        upgrade(cls.admin_dsn)
        with psycopg.connect(cls.admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
                ).format(sql.Identifier(runtime))
            )
            connection.execute(
                sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                    sql.Identifier(runtime)
                )
            )
            # Emulate only the Azure catalog response in the disposable database.
            connection.execute(
                sql.SQL("""
                CREATE FUNCTION pg_catalog.pgaadauth_list_principals(boolean)
                RETURNS TABLE (
                    rolename text, principaltype text, objectid text, tenantid text,
                    ismfa boolean, isadmin boolean
                )
                LANGUAGE sql AS $$
                    SELECT {}::text, 'service'::text, {}::text, {}::text, false, false
                    UNION ALL
                    SELECT {}::text, 'user'::text, {}::text, {}::text, false, true
                $$
            """).format(
                    sql.Literal(runtime),
                    sql.Literal(IDENTITY),
                    sql.Literal(TENANT),
                    sql.Literal(psycopg.conninfo.conninfo_to_dict(source)["user"]),
                    sql.Literal(OPERATOR),
                    sql.Literal(TENANT),
                )
            )
            installer = (
                Path(__file__).resolve().parents[1] / "poc" / "self-decision.sql"
            ).read_text(encoding="utf-8")
            for variable, value in {
                "database_host": psycopg.conninfo.conninfo_to_dict(source)["host"],
                "runtime_role": runtime,
                "tenant_id": TENANT,
                "identity_oid": IDENTITY,
                "operator_oid": OPERATOR,
            }.items():
                installer = installer.replace(f":'{variable}'", sql.Literal(value).as_string())
                installer = installer.replace(f':"{variable}"', sql.Identifier(value).as_string())
            connection.execute(installer.replace(r"\set ON_ERROR_STOP on", ""))

    @staticmethod
    def execute_admin(dsn, statement):
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(statement)

    def setUp(self):
        self.store = OrderResolutionStore(self.runtime_dsn)
        self.addCleanup(self.store.close)
        self.store.poc_enabled = True
        self.host = Mock(start=AsyncMock())
        self.service = OrderResolutionService(
            self.store,
            self.host,
            OrderResolutionRules(),
            CaseAccessPolicy(),
            hosted_mode=True,
        )

    def submit(self, actor=ACTOR):
        return asyncio.run(self.service.submit(actor, actor.subject, PAYLOAD, uuid4().hex))

    def pending(self, outcome: Decision):
        case = self.submit()
        conversation = f"conversation:{case.id}"
        handle = f"case:{case.id}:approval:v1"
        self.store.bind_hosted_principal(
            case.id,
            ACTOR,
            conversation_id=conversation,
            principal_kind="owner",
        )
        proposal = self.store.prepare_hosted_approval(case.id, handle, channel=HOSTED_CHANNEL)
        command = DecisionCommand(
            str(case.id),
            proposal.proposal_version,
            proposal.action,
            proposal.destination_id,
            handle,
            outcome,
            "workflow.approve",
            HOSTED_CHANNEL,
        )
        return case, command, conversation

    def grant(self, case_id, command, *, decision=None, expire=False):
        digest = hashlib.sha256(command.handle.encode()).hexdigest()
        with psycopg.connect(self.admin_dsn) as connection:
            result = connection.execute(
                "SELECT ors_poc.issue_grant(%s, %s, %s, %s, %s, %s, %s)",
                (
                    case_id,
                    command.proposal_version,
                    digest,
                    command.action,
                    command.destination_id,
                    (decision or command.decision).value,
                    connection.info.host,
                ),
            ).fetchone()
            if expire:
                connection.execute(
                    "UPDATE ors_poc.grant_record SET expires_at = now() WHERE case_id = %s",
                    (case_id,),
                )
            return result == (True,)

    def bind(self, case, command, conversation, actor=ACTOR):
        self.store.bind_hosted_resume_authority(
            case.id,
            actor,
            conversation_id=conversation,
            channel=HOSTED_CHANNEL,
            decision_command=command,
        )

    def record(self, case, command):
        return self.service.record_bound_decision(
            ACTOR,
            case.id,
            command.decision.value,
            proposal_version=command.proposal_version,
            action=command.action,
            destination_id=command.destination_id,
            handle=command.handle,
            channel=command.channel,
            hosted_callback=True,
        )

    def audit(self, case):
        with psycopg.connect(self.admin_dsn) as connection:
            return connection.execute(
                """
                SELECT operator_oid::text, decision FROM ors_poc.decision_audit WHERE case_id = %s
            """,
                (case.id,),
            ).fetchall()

    def test_exact_grants_approve_or_reject_and_audit_once(self):
        for outcome in (Decision.APPROVED, Decision.REJECTED):
            with self.subTest(outcome=outcome):
                case, command, conversation = self.pending(outcome)
                with self.assertRaises(AccessDenied):
                    self.bind(case, command, conversation)
                self.assertTrue(self.grant(case.id, command))
                self.assertTrue(self.grant(case.id, command))
                self.bind(case, command, conversation)
                self.assertEqual(self.record(case, command), self.record(case, command))
                action = RecordOrderResolutionAction().bind(self.store)
                self.store.apply_once(case.id, outcome is Decision.APPROVED, action)
                self.store.apply_once(case.id, outcome is Decision.APPROVED, action)
                self.store.finish_hosted(case.id)
                self.assertEqual(self.audit(case), [(OPERATOR, outcome.value)])
                self.assertEqual(
                    self.store.get(case.id).status,
                    "completed" if outcome is Decision.APPROVED else "rejected",
                )
                self.assertEqual(
                    self.store.acceptance_snapshot(case.id)["counts"]["effects"],
                    int(outcome is Decision.APPROVED),
                )

    def test_disabled_wrong_identity_expired_or_wrong_outcome_do_not_audit(self):
        impostor = Principal(TENANT, str(uuid4()), ACTOR.scopes, ACTOR.roles)
        self.store.poc_enabled = False
        with self.assertRaises(AccessDenied):
            self.submit()
        self.store.poc_enabled = True
        with self.assertRaises(AccessDenied):
            self.submit(impostor)
        with self.assertRaises(AccessDenied):
            self.submit(replace(ACTOR, tenant_id=str(uuid4())))
        with self.assertRaises(AccessDenied):
            self.submit(replace(ACTOR, roles=frozenset({"Workflow.Approver"})))
        case, command, conversation = self.pending(Decision.APPROVED)
        self.assertTrue(self.grant(case.id, command, decision=Decision.REJECTED))
        self.assertFalse(self.grant(case.id, command))
        with self.assertRaises(AccessDenied):
            self.bind(case, command, conversation)
        expired, command, conversation = self.pending(Decision.APPROVED)
        self.assertTrue(self.grant(expired.id, command, expire=True))
        with self.assertRaises(AccessDenied):
            self.bind(expired, command, conversation)
        self.assertEqual(self.audit(case), [])
        self.assertEqual(self.audit(expired), [])

    def test_runtime_cannot_change_granted_payload_or_write_protected_records(self):
        case, command, conversation = self.pending(Decision.APPROVED)
        self.assertTrue(self.grant(case.id, command))
        for statement in (
            "DELETE FROM ors_poc.grant_record WHERE case_id = %s",
            "DELETE FROM ors_poc.decision_audit WHERE case_id = %s",
            "SELECT ors_poc.issue_grant(%s, 1, 'a', 'a', 'a', 'approved', 'other-host')",
            "UPDATE public.wf_cases SET payload = '{}'::jsonb WHERE id = %s",
            "UPDATE public.order_resolution_proposals SET is_current = false WHERE case_id = %s",
        ):
            with (
                self.subTest(statement=statement),
                self.assertRaises(InsufficientPrivilege),
            ):
                with self.store.connect() as connection:
                    connection.execute(statement, (case.id,))
        self.bind(case, command, conversation)
        self.assertEqual(self.audit(case), [])

    def test_decision_and_audit_roll_back_together_on_failed_projection(self):
        case, command, conversation = self.pending(Decision.APPROVED)
        self.assertFalse(self.grant(case.id, replace(command, handle="different-request")))
        self.assertTrue(self.grant(case.id, command))
        with self.assertRaises(AccessDenied):
            self.bind(case, replace(command, handle="different-request"), conversation)
        self.bind(case, command, conversation)
        with psycopg.connect(self.admin_dsn) as connection:
            connection.execute(
                "INSERT INTO public.wf_decisions (case_id, decision, actor_id) "
                "VALUES (%s, 'rejected', %s)",
                (case.id, OPERATOR),
            )
        with self.assertRaises(Conflict):
            self.record(case, command)
        self.assertIsNone(self.store.get_decision(case.id))
        self.assertEqual(self.audit(case), [])

    def test_grant_does_not_authorize_if_runtime_can_write_its_audit(self):
        with psycopg.connect(self.admin_dsn) as connection:
            runtime = sql.Identifier(psycopg.conninfo.conninfo_to_dict(self.runtime_dsn)["user"])
            connection.execute(
                sql.SQL("GRANT INSERT ON ors_poc.decision_audit TO {}").format(runtime)
            )
        try:
            with self.assertRaises(AccessDenied):
                self.submit()
        finally:
            with psycopg.connect(self.admin_dsn) as connection:
                connection.execute(
                    sql.SQL("REVOKE INSERT ON ors_poc.decision_audit FROM {}").format(runtime)
                )
