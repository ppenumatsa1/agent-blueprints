import asyncio
import hashlib
import importlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.composition import create_app
from app.config import Settings
from app.infrastructure.identity import EntraIdentity
from app.domain.errors import AccessDenied, ActionError, Conflict, NotFound
from app.domain.models import Principal
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.application import build_application
from app.order_resolution.durability import (
    Actor,
    Decision,
    DecisionCommand,
    record_decision,
)
from app.order_resolution.effects import EffectIdentity
from app.order_resolution.host import OrderResolutionWorkflowHost
from app.order_resolution.hosted_authority import PostgresHostedAuthorityBindings
from app.order_resolution.migrations import upgrade
from app.order_resolution.persistence import (
    HOSTED_CHANNEL,
    OrderResolutionStore,
    PostgresSyntheticDestination,
)
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.service import OrderResolutionService
from app.order_resolution.workflow import build_order_resolution_workflow
from tests.test_security import API, OWNER, REVIEWER, TENANT, TokenFixture, scoped_url

HOSTED_SERVICE = "60000000-0000-4000-8000-000000000006"
HOSTED_SERVICE_ROLE = "Hosted.Workflow.Invoke"


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
            hosted_service_principal_id=HOSTED_SERVICE,
            hosted_service_app_role=HOSTED_SERVICE_ROLE,
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
        self.service_token = self.tokens.token(
            subject=HOSTED_SERVICE,
            scopes=None,
            roles=[HOSTED_SERVICE_ROLE],
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

    def hosted_case(self, order_id: str, amount: str):
        owner = Principal(
            TENANT,
            OWNER,
            frozenset({"workflow.read"}),
            frozenset(),
        )
        validated = OrderResolutionRules().validate(payload(order_id, amount, 5, [late_policy()]))
        case = self.store.create(
            owner,
            REVIEWER,
            validated,
            order_id.lower(),
            hashlib.sha256(order_id.encode("ascii")).hexdigest(),
        )
        return owner, case, self.store.persist_proposal(case.id)

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

    def test_hosted_service_endpoints_are_authorized_durable_and_idempotent(self):
        owner, case, proposal = self.hosted_case("ORDER-HOSTED-SERVICE", "185.00")
        case_id = case.id
        caller_id = "00000000-0000-0000-0000-000000000123"
        session_id = f"case:{case_id}"
        conversation_id = "conversation-hosted-service"
        binding = {
            "platform_user_id": caller_id,
            "platform_session_id": session_id,
            "platform_call_id": "platform-call-start",
            "conversation_id": conversation_id,
            "channel": HOSTED_CHANNEL,
        }
        headers = self.headers(self.service_token)
        base = f"/api/internal/hosted/v1/cases/{case_id}"
        client = self.client()
        self.addCleanup(client.close)
        start_headers = self.headers(
            self.service_token,
            f"case:{case_id}:bind-start:test",
        )

        invalid = client.post(
            f"{base}/bindings/start",
            headers=self.headers(self.owner_token, f"case:{case_id}:bind-start:test"),
            json=binding,
        )
        self.assertEqual(invalid.status_code, 401, invalid.text)
        missing_binding = client.post(
            f"{base}/bindings/start",
            headers=headers,
            json=binding,
        )
        self.assertEqual(missing_binding.status_code, 404, missing_binding.text)

        authority = PostgresHostedAuthorityBindings(self.store)
        with self.assertRaises(AccessDenied):
            authority.bind_start(
                case_id,
                Principal(TENANT, REVIEWER, frozenset({"workflow.read"}), frozenset()),
                conversation_id=conversation_id,
                channel=HOSTED_CHANNEL,
            )
        with self.assertRaises(NotFound):
            authority.load_binding(case_id)
        authority.bind_start(
            case_id,
            owner,
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
        )
        bound = client.post(f"{base}/bindings/start", headers=start_headers, json=binding)
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(bound.json()["subject"], OWNER)

        opaque_platform_repeat = client.post(
            f"{base}/bindings/start",
            headers=start_headers,
            json={
                **binding,
                "platform_user_id": "different-platform-user",
                "platform_session_id": "different-platform-session",
                "platform_call_id": "different-platform-call",
            },
        )
        self.assertEqual(opaque_platform_repeat.status_code, 200, opaque_platform_repeat.text)
        self.assertEqual(opaque_platform_repeat.json()["subject"], OWNER)

        cross_conversation = {
            **binding,
            "conversation_id": "different-conversation",
            "principal_kind": "owner",
        }
        denied = client.post(f"{base}/read", headers=headers, json=cross_conversation)
        self.assertEqual(denied.status_code, 403, denied.text)

        read_binding = {**binding, "principal_kind": "owner"}
        read = client.post(f"{base}/read", headers=headers, json=read_binding)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertNotIn("checkpoint_id", read.json())
        current = client.post(f"{base}/proposal/read", headers=headers, json=read_binding)
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["proposal_version"], proposal.proposal_version)

        request_id = f"case:{case_id}:approval:v1"
        prepare_body = {**binding, "request_id": request_id}
        prepare_headers = self.headers(
            self.service_token,
            f"case:{case_id}:approval:{request_id}",
        )
        prepared = client.post(
            f"{base}/approvals/prepare",
            headers=prepare_headers,
            json=prepare_body,
        )
        repeated_prepare = client.post(
            f"{base}/approvals/prepare",
            headers=prepare_headers,
            json={**prepare_body, "platform_call_id": "platform-call-prepare-replay"},
        )
        self.assertEqual(prepared.status_code, 200, prepared.text)
        self.assertEqual(repeated_prepare.json(), prepared.json())
        self.assertIsNone(self.store.get(case_id).checkpoint_id)

        proposal = self.store.get_current_proposal(str(case_id))
        decision_command = DecisionCommand(
            case_id=str(case_id),
            proposal_version=proposal.proposal_version,
            action=proposal.action,
            destination_id=proposal.destination_id,
            handle=request_id,
            decision=Decision.APPROVED,
            scope="workflow.approve",
            channel=HOSTED_CHANNEL,
        )
        reviewer = Principal(
            TENANT,
            REVIEWER,
            frozenset({"workflow.read", "workflow.approve"}),
            frozenset({"Workflow.Approver"}),
        )
        resume_headers = self.headers(
            self.service_token,
            f"case:{case_id}:bind-resume:test",
        )
        reviewer_binding = {
            **binding,
        }
        with self.assertRaises(AccessDenied):
            authority.bind_resume(
                case_id,
                Principal(
                    TENANT,
                    OWNER,
                    frozenset({"workflow.read", "workflow.approve"}),
                    frozenset({"Workflow.Approver"}),
                ),
                conversation_id=conversation_id,
                channel=HOSTED_CHANNEL,
                decision_command=decision_command,
            )
            with self.assertRaises(Conflict):
                authority.bind_resume(
                    case_id,
                    reviewer,
                    conversation_id=conversation_id,
                    channel=HOSTED_CHANNEL,
                    decision_command=DecisionCommand(
                        case_id=str(case_id),
                        proposal_version=proposal.proposal_version,
                        action=proposal.action,
                        destination_id=proposal.destination_id,
                        handle=request_id,
                        decision=Decision.REJECTED,
                        scope="workflow.approve",
                        channel=HOSTED_CHANNEL,
                    ),
                )
        with self.assertRaises(AccessDenied):
            authority.bind_resume(
                case_id,
                reviewer,
                conversation_id="wrong-conversation",
                channel=HOSTED_CHANNEL,
                decision_command=decision_command,
            )
        authority.bind_resume(
            case_id,
            reviewer,
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
            decision_command=decision_command,
        )
        self.assertEqual(self.store.get(case_id).status, "pending")
        self.assertIsNone(self.store.get_decision(case_id))
        resumed = client.post(
            f"{base}/bindings/resume",
            headers=resume_headers,
            json=reviewer_binding,
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["subject"], REVIEWER)
        self.assertEqual(self.store.get(case_id).status, "pending")
        self.assertIsNone(self.store.get_decision(case_id))
        opaque_platform_resume = client.post(
            f"{base}/bindings/resume",
            headers=resume_headers,
            json={
                **reviewer_binding,
                "platform_user_id": "different-platform-user",
                "platform_session_id": "different-platform-session",
                "platform_call_id": "different-platform-call",
            },
        )
        self.assertEqual(opaque_platform_resume.status_code, 200, opaque_platform_resume.text)
        self.assertEqual(opaque_platform_resume.json()["subject"], REVIEWER)
        revoked_owner = client.post(
            f"{base}/bindings/start",
            headers=start_headers,
            json={**binding, "platform_call_id": "platform-call-after-resume"},
        )
        self.assertEqual(revoked_owner.status_code, 403, revoked_owner.text)
        decision_body = {
            **reviewer_binding,
            "proposal_version": proposal.proposal_version,
            "action": proposal.action,
            "destination_id": proposal.destination_id,
            "handle": request_id,
            "decision": "approved",
        }
        decision_headers = self.headers(
            self.service_token,
            f"case:{case_id}:decision:{proposal.proposal_version}:approved",
        )
        decided = client.post(
            f"{base}/decisions/claim",
            headers=decision_headers,
            json=decision_body,
        )
        repeated_decision = client.post(
            f"{base}/decisions/claim",
            headers=decision_headers,
            json={**decision_body, "platform_call_id": "platform-call-decision-replay"},
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertEqual(repeated_decision.json(), decided.json())
        conflict = client.post(
            f"{base}/decisions/claim",
            headers=decision_headers,
            json={
                **decision_body,
                "decision": "rejected",
                "platform_call_id": "platform-call-decision-conflict",
            },
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)

        effect_body = {**reviewer_binding, "mode": "approved"}
        effect_headers = self.headers(
            self.service_token,
            f"case:{case_id}:action:approved",
        )
        first_effect = client.post(
            f"{base}/effects/apply",
            headers=effect_headers,
            json=effect_body,
        )
        repeated_effect = client.post(
            f"{base}/effects/apply",
            headers=effect_headers,
            json={**effect_body, "platform_call_id": "platform-call-effect-replay"},
        )
        self.assertEqual(first_effect.status_code, 200, first_effect.text)
        self.assertEqual(repeated_effect.status_code, 200, repeated_effect.text)

        finish_body = {**reviewer_binding, "mode": "approved"}
        finish_headers = self.headers(
            self.service_token,
            f"case:{case_id}:completion:approved",
        )
        first_finish = client.post(
            f"{base}/finish",
            headers=finish_headers,
            json=finish_body,
        )
        client.close()
        client = self.client()
        self.addCleanup(client.close)
        repeated_finish = client.post(
            f"{base}/finish",
            headers=finish_headers,
            json={**finish_body, "platform_call_id": "platform-call-finish-replay"},
        )
        self.assertEqual(first_finish.status_code, 200, first_finish.text)
        self.assertEqual(repeated_finish.json(), first_finish.json())
        completed = self.store.get(case_id)
        self.assertEqual((completed.status, completed.execution_complete), ("completed", True))
        self.assertIsNone(completed.checkpoint_id)
        self.assertIsNone(completed.terminal_checkpoint_id)
        self.assertEqual(self.database_counts(case_id)["actions"], 1)
        self.assertEqual(self.durability_counts(case_id)["synthetic_effects"], 1)

        restarted = OrderResolutionStore(self.settings.database_url)
        self.addCleanup(restarted.close)
        restart_client = TestClient(
            create_app(
                self.settings,
                build_application(),
                store=restarted,
                identity=self.identity,
            )
        )
        self.addCleanup(restart_client.close)
        restarted_effect = restart_client.post(
            f"{base}/effects/apply",
            headers=effect_headers,
            json={
                **effect_body,
                "platform_call_id": "platform-call-effect-after-restart",
            },
        )
        self.assertEqual(restarted_effect.status_code, 200, restarted_effect.text)
        components = build_application()

        class ReplayAuthorityHost:
            async def start(self, case_id, actor):
                raise AssertionError("start was not expected")

            async def resume(self, case_id, actor, decision_command):
                PostgresHostedAuthorityBindings(restarted).bind_resume(
                    case_id,
                    actor,
                    conversation_id=conversation_id,
                    channel=HOSTED_CHANNEL,
                    decision_command=decision_command,
                )

        replay_service = OrderResolutionService(
            restarted,
            ReplayAuthorityHost(),
            components.rules,
            components.policy,
            hosted_mode=True,
        )
        replayed = asyncio.run(
            replay_service.decide_bound(
                reviewer,
                case_id,
                "approved",
                proposal_version=proposal.proposal_version,
                action=proposal.action,
                destination_id=proposal.destination_id,
                handle=request_id,
                channel=HOSTED_CHANNEL,
            )
        )
        self.assertEqual((replayed.status, replayed.execution_complete), ("completed", True))
        with self.assertRaises(Conflict):
            asyncio.run(
                replay_service.decide_bound(
                    reviewer,
                    case_id,
                    "rejected",
                    proposal_version=proposal.proposal_version,
                    action=proposal.action,
                    destination_id=proposal.destination_id,
                    handle=request_id,
                    channel=HOSTED_CHANNEL,
                )
            )
        with self.assertRaises(AccessDenied):
            asyncio.run(
                replay_service.decide_bound(
                    owner,
                    case_id,
                    "approved",
                    proposal_version=proposal.proposal_version,
                    action=proposal.action,
                    destination_id=proposal.destination_id,
                    handle=request_id,
                    channel=HOSTED_CHANNEL,
                )
            )
        self.assertEqual(self.durability_counts(case_id)["denials"], 1)
        restarted_read = restart_client.post(
            f"{base}/read",
            headers=headers,
            json={**reviewer_binding, "principal_kind": "reviewer"},
        )
        self.assertEqual(restarted_read.status_code, 200, restarted_read.text)
        self.assertTrue(restarted_read.json()["execution_complete"])

    def test_hosted_rejection_and_automatic_completion_keep_checkpoints_external(self):
        reviewer = Principal(
            TENANT,
            REVIEWER,
            frozenset({"workflow.read", "workflow.approve"}),
            frozenset({"Workflow.Approver"}),
        )
        owner, rejected_case, rejected_proposal = self.hosted_case("ORDER-HOSTED-REJECT", "185.00")
        rejected_conversation = "conversation-hosted-rejection"
        self.store.bind_hosted_principal(
            rejected_case.id,
            owner,
            conversation_id=rejected_conversation,
            principal_kind="owner",
        )
        request_id = f"case:{rejected_case.id}:approval:v1"
        self.store.prepare_hosted_approval(
            rejected_case.id,
            request_id,
            channel=HOSTED_CHANNEL,
        )

        restarted = OrderResolutionStore(self.settings.database_url)
        self.addCleanup(restarted.close)
        action = RecordOrderResolutionAction().bind(restarted)

        class HostedDecisionStore:
            get_current_proposal = restarted.get_current_proposal
            claim_decision = restarted.claim_hosted_decision

        command = DecisionCommand(
            case_id=str(rejected_case.id),
            proposal_version=rejected_proposal.proposal_version,
            action=rejected_proposal.action,
            destination_id=rejected_proposal.destination_id,
            handle=request_id,
            decision=Decision.REJECTED,
            scope="workflow.approve",
            channel=HOSTED_CHANNEL,
        )
        PostgresHostedAuthorityBindings(restarted).bind_resume(
            rejected_case.id,
            reviewer,
            conversation_id=rejected_conversation,
            channel=HOSTED_CHANNEL,
            decision_command=command,
        )
        decision = record_decision(
            HostedDecisionStore(),
            proposal=restarted.get_current_proposal(str(rejected_case.id)),
            actor=Actor(
                reviewer.tenant_id,
                reviewer.subject,
                reviewer.scopes,
                reviewer.roles,
            ),
            command=command,
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(restarted.claim_hosted_decision(decision), decision)
        restarted.apply_once(rejected_case.id, False, action)
        restarted.finish_hosted(rejected_case.id)
        restarted.finish_hosted(rejected_case.id)
        rejected = restarted.get(rejected_case.id)
        self.assertEqual((rejected.status, rejected.execution_complete), ("rejected", True))
        self.assertIsNone(rejected.checkpoint_id)
        self.assertIsNone(rejected.terminal_checkpoint_id)
        components = build_application()

        class RejectedReplayAuthorityHost:
            async def start(self, case_id, actor):
                raise AssertionError("start was not expected")

            async def resume(self, case_id, actor, decision_command):
                PostgresHostedAuthorityBindings(restarted).bind_resume(
                    case_id,
                    actor,
                    conversation_id=rejected_conversation,
                    channel=HOSTED_CHANNEL,
                    decision_command=decision_command,
                )

        replayed_rejection = asyncio.run(
            OrderResolutionService(
                restarted,
                RejectedReplayAuthorityHost(),
                components.rules,
                components.policy,
                hosted_mode=True,
            ).decide_bound(
                reviewer,
                rejected_case.id,
                "rejected",
                proposal_version=rejected_proposal.proposal_version,
                action=rejected_proposal.action,
                destination_id=rejected_proposal.destination_id,
                handle=request_id,
                channel=HOSTED_CHANNEL,
            )
        )
        self.assertEqual(
            (replayed_rejection.status, replayed_rejection.execution_complete),
            ("rejected", True),
        )

        owner, automatic_case, _ = self.hosted_case("ORDER-HOSTED-AUTOMATIC", "8.00")
        restarted.bind_hosted_principal(
            automatic_case.id,
            owner,
            conversation_id="conversation-hosted-automatic",
            principal_kind="owner",
        )
        restarted.apply_automatic(automatic_case.id, action)
        restarted.apply_automatic(automatic_case.id, action)
        restarted.finish_hosted(automatic_case.id)
        automatic = restarted.get(automatic_case.id)
        self.assertEqual((automatic.status, automatic.execution_complete), ("completed", True))
        self.assertIsNone(automatic.checkpoint_id)
        self.assertIsNone(automatic.terminal_checkpoint_id)

    def test_hosted_service_effect_modes_preserve_rejection_and_automatic_outcomes(
        self,
    ):
        client = self.client()
        self.addCleanup(client.close)

        for mode, amount, expected_status, expected_actions in (
            ("automatic", "8.00", "completed", 1),
            ("rejected", "185.00", "rejected", 0),
        ):
            with self.subTest(mode=mode):
                owner, case, proposal = self.hosted_case(
                    f"ORDER-HOSTED-{mode.upper()}",
                    amount,
                )
                case_id = case.id
                binding = {
                    "platform_user_id": "platform-api-workload",
                    "platform_session_id": f"platform-session:{case_id}",
                    "platform_call_id": f"platform-call:{mode}",
                    "conversation_id": f"conversation-{mode}",
                    "channel": HOSTED_CHANNEL,
                }
                base = f"/api/internal/hosted/v1/cases/{case_id}"
                authority = PostgresHostedAuthorityBindings(self.store)
                authority.bind_start(
                    case_id,
                    owner,
                    conversation_id=binding["conversation_id"],
                    channel=HOSTED_CHANNEL,
                )
                self.assertEqual(
                    client.post(
                        f"{base}/bindings/start",
                        headers=self.headers(
                            self.service_token,
                            f"case:{case_id}:bind-start:{mode}",
                        ),
                        json=binding,
                    ).status_code,
                    200,
                )
                active_binding = binding
                if mode == "rejected":
                    request_id = f"case:{case_id}:approval:v1"
                    self.assertEqual(
                        client.post(
                            f"{base}/approvals/prepare",
                            headers=self.headers(
                                self.service_token,
                                f"case:{case_id}:approval:{request_id}",
                            ),
                            json={**binding, "request_id": request_id},
                        ).status_code,
                        200,
                    )
                    proposal = self.store.get_current_proposal(str(case_id))
                    command = DecisionCommand(
                        case_id=str(case_id),
                        proposal_version=proposal.proposal_version,
                        action=proposal.action,
                        destination_id=proposal.destination_id,
                        handle=request_id,
                        decision=Decision.REJECTED,
                        scope="workflow.approve",
                        channel=HOSTED_CHANNEL,
                    )
                    reviewer = Principal(
                        TENANT,
                        REVIEWER,
                        frozenset({"workflow.read", "workflow.approve"}),
                        frozenset({"Workflow.Approver"}),
                    )
                    active_binding = binding
                    authority.bind_resume(
                        case_id,
                        reviewer,
                        conversation_id=active_binding["conversation_id"],
                        channel=HOSTED_CHANNEL,
                        decision_command=command,
                    )
                    self.assertEqual(
                        client.post(
                            f"{base}/bindings/resume",
                            headers=self.headers(
                                self.service_token,
                                f"case:{case_id}:bind-resume:{mode}",
                            ),
                            json=active_binding,
                        ).status_code,
                        200,
                    )
                    self.assertEqual(
                        client.post(
                            f"{base}/decisions/claim",
                            headers=self.headers(
                                self.service_token,
                                f"case:{case_id}:decision:{proposal.proposal_version}:rejected",
                            ),
                            json={
                                **active_binding,
                                "proposal_version": proposal.proposal_version,
                                "action": proposal.action,
                                "destination_id": proposal.destination_id,
                                "handle": request_id,
                                "decision": "rejected",
                            },
                        ).status_code,
                        200,
                    )
                effect = client.post(
                    f"{base}/effects/apply",
                    headers=self.headers(
                        self.service_token,
                        f"case:{case_id}:action:{mode}",
                    ),
                    json={**active_binding, "mode": mode},
                )
                finish = client.post(
                    f"{base}/finish",
                    headers=self.headers(
                        self.service_token,
                        f"case:{case_id}:completion:{mode}",
                    ),
                    json={**active_binding, "mode": mode},
                )
                self.assertEqual(effect.status_code, 200, effect.text)
                self.assertEqual(finish.status_code, 200, finish.text)
                stored = self.store.get(case_id)
                self.assertEqual(stored.status, expected_status)
                self.assertTrue(stored.execution_complete)
                self.assertIsNone(stored.checkpoint_id)
                self.assertIsNone(stored.terminal_checkpoint_id)
                self.assertEqual(self.database_counts(case_id)["actions"], expected_actions)

    def test_hosted_human_command_persists_intent_before_callback_decision(self):
        owner, case, proposal = self.hosted_case("ORDER-HOSTED-INTENT", "185.00")
        request_id = f"case:{case.id}:approval:v1"
        conversation_id = "conversation-hosted-intent"
        authority = PostgresHostedAuthorityBindings(self.store)
        authority.bind_start(
            case.id,
            owner,
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
        )
        self.store.prepare_hosted_approval(case.id, request_id, channel=HOSTED_CHANNEL)

        class IntentOnlyHost:
            async def start(self, case_id, actor):
                raise AssertionError("start was not expected")

            async def resume(self, case_id, actor, decision_command):
                authority.bind_resume(
                    case_id,
                    actor,
                    conversation_id=conversation_id,
                    channel=HOSTED_CHANNEL,
                    decision_command=decision_command,
                )

        components = build_application()
        service = OrderResolutionService(
            self.store,
            IntentOnlyHost(),
            components.rules,
            components.policy,
            hosted_mode=True,
        )
        reviewer = Principal(
            TENANT,
            REVIEWER,
            frozenset({"workflow.read", "workflow.approve"}),
            frozenset({"Workflow.Approver"}),
        )
        result = asyncio.run(
            service.decide_bound(
                reviewer,
                case.id,
                "approved",
                proposal_version=proposal.proposal_version,
                action=proposal.action,
                destination_id=proposal.destination_id,
                handle=request_id,
                channel=HOSTED_CHANNEL,
            )
        )
        self.assertEqual(result.status, "pending")
        self.assertIsNone(self.store.get_decision(case.id))
        verified = self.store.authorize_hosted_resume(
            case.id,
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
        )
        self.assertEqual(verified.subject, REVIEWER)

    def test_agent_a_http_business_store_composes_over_loopback_and_postgres(self):
        agent_a_source = os.environ.get("ORDER_RESOLUTION_AGENT_A_SOURCE")
        if not agent_a_source:
            self.skipTest("ORDER_RESOLUTION_AGENT_A_SOURCE does not select Agent A source.")

        import uvicorn

        source_root = Path(agent_a_source) / "order_resolution_hosted"
        package_temp = tempfile.TemporaryDirectory()
        self.addCleanup(package_temp.cleanup)
        package_root = Path(package_temp.name) / "order_resolution_hosted"
        package_root.mkdir()
        (package_root / "__init__.py").write_text("", encoding="utf-8")
        for module_name in ("application", "business", "client", "bridge"):
            shutil.copy2(source_root / f"{module_name}.py", package_root)
        sys.path.insert(0, package_temp.name)
        importlib.invalidate_caches()
        loaded_modules = [
            "order_resolution_hosted",
            "order_resolution_hosted.application",
            "order_resolution_hosted.business",
            "order_resolution_hosted.client",
            "order_resolution_hosted.bridge",
        ]
        for module_name in loaded_modules:
            sys.modules.pop(module_name, None)

        def unload_backend_bridge():
            for module_name in loaded_modules:
                sys.modules.pop(module_name, None)
            sys.path.remove(package_temp.name)

        self.addCleanup(unload_backend_bridge)
        from order_resolution_hosted.application import CallerContext
        from order_resolution_hosted.bridge import ResponsesWorkflowHost
        from order_resolution_hosted.business import HttpHostedBusinessStore
        from order_resolution_hosted.client import (
            OperationClaim,
            OperationRecord,
            OperationStatus,
            ResponsesClient,
        )

        from app.order_resolution.hosted_journal import PostgresOperationJournal

        hosted_settings = Settings(
            TENANT,
            API,
            ("postgresql://runtime@database.postgres.database.azure.com/app?sslmode=verify-full"),
            None,
            host_mode="hosted",
            hosted_workflow_endpoint=(
                "https://example.test/agents/order/endpoint/responses?api-version=v1"
            ),
            hosted_conversation_endpoint=(
                "https://example.test/agents/order/endpoint/conversations?api-version=v1"
            ),
            hosted_workflow_scope="https://ai.azure.com/.default",
            api_managed_identity_client_id="50000000-0000-4000-8000-000000000005",
            hosted_service_principal_id=HOSTED_SERVICE,
            hosted_service_app_role=HOSTED_SERVICE_ROLE,
            database_auth_mode="managed-identity",
            database_managed_identity_client_id="50000000-0000-4000-8000-000000000005",
            database_tls_mode="verify-full",
            database_tls_root_cert="system",
        )
        hosted_application = create_app(
            hosted_settings,
            build_application(),
            store=self.store,
            identity=self.identity,
        )
        self.assertIsInstance(hosted_application.state.service.host, ResponsesWorkflowHost)

        owner_actor, case, proposal = self.hosted_case("ORDER-HOSTED-AGENT-A", "185.00")
        application = create_app(
            self.settings,
            build_application(),
            store=self.store,
            identity=self.identity,
        )
        foundry_calls: list[tuple[str, dict]] = []

        @application.post("/conversations")
        def create_conversation(payload: dict) -> dict:
            foundry_calls.append(("conversation", payload))
            return {"id": "conversation-agent-a"}

        @application.post("/responses")
        def create_response(payload: dict) -> dict:
            foundry_calls.append(("response", payload))
            return {"id": f"response-{len(foundry_calls)}"}

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="127.0.0.1",
                port=port,
                log_level="error",
                lifespan="off",
            )
        )
        thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [listener]},
            daemon=True,
        )
        thread.start()

        def stop_server():
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()

        self.addCleanup(stop_server)
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.01)
        self.assertTrue(server.started)

        token = self.service_token

        class StaticTokenProvider:
            @staticmethod
            def authorization_header() -> str:
                return f"Bearer {token}"

        endpoint = f"http://127.0.0.1:{port}/api/internal/hosted/v1"
        api = HttpHostedBusinessStore(endpoint, StaticTokenProvider())
        conversation_id = "conversation-agent-a"
        session_id = "platform-session-agent-a"
        owner = CallerContext("platform-api-workload", session_id, "call-start")
        reviewer = CallerContext("platform-api-workload", session_id, "call-resume")
        authority = PostgresHostedAuthorityBindings(self.store)

        authority.bind_start(
            case.id,
            owner_actor,
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
        )
        owner_principal = api.resolve_start_principal(
            case_id=case.id,
            caller=owner,
            conversation_id=conversation_id,
        )
        owner_store = api.for_binding(owner, conversation_id, "owner")
        prepared = owner_store.prepare_hosted_approval(
            case.id,
            f"case:{case.id}:approval:v1",
            channel=HOSTED_CHANNEL,
        )
        decision_command = DecisionCommand(
            case_id=str(case.id),
            proposal_version=proposal.proposal_version,
            action=proposal.action,
            destination_id=proposal.destination_id,
            handle=f"case:{case.id}:approval:v1",
            decision=Decision.APPROVED,
            scope="workflow.approve",
            channel=HOSTED_CHANNEL,
        )
        reviewer_actor = Principal(
            TENANT,
            REVIEWER,
            frozenset({"workflow.read", "workflow.approve"}),
            frozenset({"Workflow.Approver"}),
        )
        authority.bind_resume(
            case.id,
            reviewer_actor,
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
            decision_command=decision_command,
        )
        reviewer_principal = api.authorize_resume(
            case_id=case.id,
            caller=reviewer,
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
        )
        reviewer_store = api.for_binding(reviewer, conversation_id, "reviewer")
        decision = reviewer_store.record_hosted_decision(decision_command)
        reviewer_store.apply_once(case.id, True, object())
        reviewer_store.finish_hosted(case.id)

        restarted_api = HttpHostedBusinessStore(endpoint, StaticTokenProvider())
        restarted_store = restarted_api.for_binding(
            CallerContext(
                "platform-api-workload",
                session_id,
                "call-resume-after-restart",
            ),
            conversation_id,
            "reviewer",
        )
        restarted_store.apply_once(case.id, True, object())
        restarted_store.finish_hosted(case.id)

        journal = PostgresOperationJournal(
            self.store,
            record_type=OperationRecord,
            claim_type=OperationClaim,
            status_type=OperationStatus,
        )
        probe = journal.claim(
            f"case:{case.id}:decision:journal-probe",
            hashlib.sha256(b"journal-probe").hexdigest(),
        )
        duplicate_probe = journal.claim(
            f"case:{case.id}:decision:journal-probe",
            hashlib.sha256(b"journal-probe").hexdigest(),
        )
        self.assertIsInstance(probe, OperationClaim)
        self.assertIs(type(probe.record.status), OperationStatus)
        self.assertTrue(probe.acquired)
        self.assertFalse(duplicate_probe.acquired)

        responses = ResponsesClient(
            f"http://127.0.0.1:{port}/responses?api-version=v1",
            journal,
            conversation_endpoint=(f"http://127.0.0.1:{port}/conversations?api-version=v1"),
            token_provider=StaticTokenProvider(),
        )
        conversation_operation = f"case:{case.id}:conversation"
        start_operation = f"case:{case.id}:start"
        decision_operation = f"case:{case.id}:decision:{proposal.proposal_version}"
        responses_binding = responses.create_conversation(
            operation_id=conversation_operation,
        )
        start_id = responses.start(
            operation_id=start_operation,
            binding=responses_binding,
            case_id=str(case.id),
        )
        repeated_start_id = responses.start(
            operation_id=start_operation,
            binding=responses_binding,
            case_id=str(case.id),
        )
        request_id = f"case:{case.id}:approval:v1"
        decision_payload = {
            "case_id": str(case.id),
            "proposal_version": proposal.proposal_version,
            "action": proposal.action,
            "destination_id": proposal.destination_id,
            "handle": request_id,
            "decision": "approved",
            "conversation_id": responses_binding.conversation_id,
            "channel": HOSTED_CHANNEL,
        }
        response_id = responses.resume(
            operation_id=decision_operation,
            binding=responses_binding,
            request_id=request_id,
            decision=decision_payload,
        )
        restarted_responses = ResponsesClient(
            f"http://127.0.0.1:{port}/responses?api-version=v1",
            PostgresOperationJournal(self.store),
            conversation_endpoint=(f"http://127.0.0.1:{port}/conversations?api-version=v1"),
            token_provider=StaticTokenProvider(),
        )
        self.assertEqual(
            restarted_responses.create_conversation(
                operation_id=conversation_operation,
            ).conversation_id,
            responses_binding.conversation_id,
        )
        self.assertEqual(
            restarted_responses.start(
                operation_id=start_operation,
                binding=responses_binding,
                case_id=str(case.id),
            ),
            start_id,
        )
        self.assertEqual(
            restarted_responses.resume(
                operation_id=decision_operation,
                binding=responses_binding,
                request_id=request_id,
                decision=decision_payload,
            ),
            response_id,
        )
        composed_host = ResponsesWorkflowHost(restarted_responses, authority)
        responses_before_terminal_replay = len(foundry_calls)
        asyncio.run(composed_host.resume(case.id, reviewer_actor, decision_command))
        self.assertEqual(len(foundry_calls), responses_before_terminal_replay)
        with self.assertRaises(Conflict):
            asyncio.run(
                composed_host.resume(
                    case.id,
                    reviewer_actor,
                    DecisionCommand(
                        case_id=str(case.id),
                        proposal_version=proposal.proposal_version,
                        action=proposal.action,
                        destination_id=proposal.destination_id,
                        handle=request_id,
                        decision=Decision.REJECTED,
                        scope="workflow.approve",
                        channel=HOSTED_CHANNEL,
                    ),
                )
            )
        with self.assertRaises(AccessDenied):
            asyncio.run(composed_host.resume(case.id, owner_actor, decision_command))

        self.assertEqual(owner_principal.subject, OWNER)
        self.assertEqual(reviewer_principal.subject, REVIEWER)
        self.assertEqual(prepared.proposal_version, proposal.proposal_version)
        self.assertEqual(decision.actor_id, REVIEWER)
        self.assertEqual(start_id, repeated_start_id)
        self.assertEqual(
            [kind for kind, _ in foundry_calls],
            ["conversation", "response", "response"],
        )
        self.assertEqual(
            foundry_calls[1][1]["input"],
            f'{{"case_id":"{case.id}"}}',
        )
        self.assertNotIn("agent_session_id", foundry_calls[1][1])
        self.assertNotIn("agent_session_id", foundry_calls[2][1])
        self.assertEqual(foundry_calls[1][1]["metadata"], {"operation_id": start_operation})
        self.assertEqual(foundry_calls[2][1]["metadata"], {"operation_id": decision_operation})
        self.assertEqual(foundry_calls[2][1]["input"][0]["type"], "function_call_output")
        stored = self.store.get(case.id)
        self.assertEqual((stored.status, stored.execution_complete), ("completed", True))
        self.assertIsNone(stored.checkpoint_id)
        self.assertIsNone(stored.terminal_checkpoint_id)
        self.assertEqual(self.database_counts(case.id)["actions"], 1)
        self.assertEqual(self.database_counts(case.id)["decisions"], 1)

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
                    (
                        completed.status,
                        completed.decision,
                        completed.execution_complete,
                    ),
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
