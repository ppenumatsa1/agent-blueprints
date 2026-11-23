import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from psycopg.types.json import Jsonb

from app.domain.errors import AccessDenied, ActionError, Conflict, NotFound
from app.domain.models import Principal, TransactionalAction
from app.infrastructure.store import PostgresStore, _case
from app.order_resolution.durability import (
    Decision,
    DecisionCommand,
    DecisionRecord,
    Proposal,
    RequestClaim,
)
from app.order_resolution.effects import (
    EffectIdentity,
    EffectLedgerRecord,
    EffectRequest,
    EffectStatus,
    Observation,
)


_CASE_FOR_UPDATE = """
    SELECT c.*, d.decision
    FROM wf_cases AS c
    LEFT JOIN wf_decisions AS d ON d.case_id = c.id
    WHERE c.id = %s
    FOR UPDATE OF c
"""
_DIGEST = re.compile(r"[0-9a-f]{64}")
DECISION_TTL = timedelta(minutes=15)
SYNTHETIC_TOOL_IDENTITY = "order-resolution-synthetic-tool-v1"
HOSTED_CHANNEL = "foundry-responses"


@dataclass(frozen=True)
class HostedOperation:
    operation_id: str
    case_id: UUID
    operation_kind: str
    request_digest: str
    status: str
    remote_id: str | None


@dataclass(frozen=True)
class HostedOperationClaim:
    record: HostedOperation
    acquired: bool


@dataclass(frozen=True)
class HostedConversationBinding:
    conversation_id: str


def _proposal(row) -> Proposal:
    return Proposal(
        case_id=str(row["case_id"]),
        proposal_version=row["proposal_version"],
        tenant_id=row["tenant_id"],
        owner_id=row["owner_id"],
        reviewer_id=row["reviewer_id"],
        input_digest=row["input_digest"],
        policy_evidence_digest=row["policy_evidence_digest"],
        policy_version=row["policy_version"],
        action=row["action"],
        destination_id=row["destination_id"],
        approval_required=row["approval_required"],
        reason_codes=tuple(row["reason_codes"]),
        decision_handle_digest=row["decision_handle_digest"],
        decision_expires_at=row["decision_expires_at"],
        decision_channel=row["decision_channel"],
    )


def _decision(row) -> DecisionRecord:
    return DecisionRecord(
        case_id=str(row["case_id"]),
        proposal_version=row["proposal_version"],
        action=row["action"],
        destination_id=row["destination_id"],
        decision=Decision(row["decision"]),
        actor_id=row["actor_id"],
        tenant_id=row["tenant_id"],
        scope=row["decision_scope"],
        channel=row["decision_channel"],
        decided_at=row["decided_at"],
    )


def _effect(row) -> EffectLedgerRecord:
    identity = EffectIdentity(
        str(row["case_id"]),
        row["proposal_version"],
        row["action"],
        row["destination_id"],
    )
    request = EffectRequest(
        identity=identity,
        key=row["effect_key"],
        digest=row["request_digest"],
        body=bytes(row["request_body"]),
    )
    return EffectLedgerRecord(
        request=request,
        status=EffectStatus(row["status"]),
        result_digest=row["result_digest"],
    )


class OrderResolutionStore(PostgresStore):
    """PostgreSQL business state correlated with, but separate from, MAF checkpoints."""

    acceptance_faults = None

    def connect(self):
        if self.acceptance_faults is not None and self.acceptance_faults.postgres_transient():
            raise RuntimeError("Injected synthetic PostgreSQL transient failure.")
        return super().connect()

    def create(
        self,
        actor: Principal,
        reviewer_id: str,
        payload: dict,
        idempotency_key: str,
        input_digest: str,
    ):
        case = super().create(actor, reviewer_id, payload, idempotency_key, input_digest)
        claim = RequestClaim(
            actor.tenant_id,
            actor.subject,
            idempotency_key,
            input_digest,
            str(case.id),
        )
        recorded = self.claim_request(claim)
        if recorded != claim:
            raise Conflict("The request identity is bound to a different case.")
        return case

    def claim_request(self, claim: RequestClaim) -> RequestClaim:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO order_resolution_requests
                    (tenant_id, owner_id, request_key, request_digest, case_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    claim.tenant_id,
                    claim.owner_id,
                    claim.request_key,
                    claim.request_digest,
                    UUID(claim.case_id),
                ),
            )
            row = connection.execute(
                """
                SELECT tenant_id, owner_id, request_key, request_digest, case_id
                FROM order_resolution_requests
                WHERE tenant_id = %s AND owner_id = %s AND request_key = %s
                """,
                (claim.tenant_id, claim.owner_id, claim.request_key),
            ).fetchone()
        if row is None:
            raise Conflict("The request claim could not be verified.")
        return RequestClaim(
            row["tenant_id"],
            row["owner_id"],
            row["request_key"],
            row["request_digest"],
            str(row["case_id"]),
        )

    def persist_proposal(self, case_id: UUID) -> Proposal:
        case = self.get(case_id)
        value = case.payload.get("proposal")
        if not isinstance(value, dict):
            raise Conflict("An authoritative proposal is required.")
        requested = Proposal(
            case_id=str(case.id),
            proposal_version=value["version"],
            tenant_id=case.tenant_id,
            owner_id=case.owner_id,
            reviewer_id=case.reviewer_id,
            input_digest=value["input_digest"],
            policy_evidence_digest=value["policy_evidence_digest"],
            policy_version=value["policy_id"],
            action=value["action"],
            destination_id=value["destination_id"],
            approval_required=value["approval_required"],
            reason_codes=tuple(value["reason_codes"]),
            decision_handle_digest=None,
            decision_expires_at=None,
            decision_channel=None,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO order_resolution_proposals
                    (case_id, proposal_version, tenant_id, owner_id, reviewer_id,
                     input_digest, policy_evidence_digest, policy_version, action,
                     destination_id, approval_required, reason_codes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    case_id,
                    requested.proposal_version,
                    requested.tenant_id,
                    requested.owner_id,
                    requested.reviewer_id,
                    requested.input_digest,
                    requested.policy_evidence_digest,
                    requested.policy_version,
                    requested.action,
                    requested.destination_id,
                    requested.approval_required,
                    Jsonb(list(requested.reason_codes)),
                ),
            )
            current = connection.execute(
                """
                SELECT * FROM order_resolution_proposals
                WHERE case_id = %s AND is_current
                FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if current is None:
                raise Conflict("The current proposal could not be verified.")
            recorded = _proposal(current)
            if recorded != requested:
                raise Conflict("The current proposal conflicts with the submitted request.")
            return recorded

    def bind_decision_handle(
        self,
        case_id: UUID,
        handle: str,
        *,
        channel: str = "api",
        now: datetime | None = None,
    ) -> Proposal:
        if not handle:
            raise Conflict("The native pending request identity is required.")
        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        digest = hashlib.sha256(handle.encode("utf-8")).hexdigest()
        expires = current_time + DECISION_TTL
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM order_resolution_proposals
                WHERE case_id = %s AND is_current
                FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                raise Conflict("The current proposal is missing.")
            proposal = _proposal(row)
            if not proposal.approval_required:
                raise Conflict("The proposal does not accept a decision binding.")
            if proposal.decision_handle_digest is None:
                connection.execute(
                    """
                    UPDATE order_resolution_proposals
                    SET decision_handle_digest = %s, decision_expires_at = %s,
                        decision_channel = %s
                    WHERE case_id = %s AND proposal_version = %s
                    """,
                    (digest, expires, channel, case_id, proposal.proposal_version),
                )
            elif proposal.decision_handle_digest != digest or proposal.decision_channel != channel:
                raise Conflict("The proposal is bound to a different native pending request.")
        return self.get_current_proposal(str(case_id))

    def get_current_proposal(self, case_id: str) -> Proposal:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM order_resolution_proposals WHERE case_id = %s AND is_current",
                (UUID(case_id),),
            ).fetchone()
        if row is None:
            raise Conflict("The current proposal is missing.")
        return _proposal(row)

    def get_decision(self, case_id: UUID) -> DecisionRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM order_resolution_decisions
                WHERE case_id = %s
                ORDER BY proposal_version DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
        return _decision(row) if row is not None else None

    def claim_decision(self, decision: DecisionRecord) -> DecisionRecord:
        case_id = UUID(decision.case_id)
        with self.connect() as connection:
            proposal = connection.execute(
                """
                SELECT * FROM order_resolution_proposals
                WHERE case_id = %s AND proposal_version = %s AND is_current
                FOR UPDATE
                """,
                (case_id, decision.proposal_version),
            ).fetchone()
            if proposal is None or _proposal(proposal).action_identity != decision.action_identity:
                raise Conflict("The decision does not match the current proposal.")
            connection.execute(
                """
                INSERT INTO order_resolution_decisions
                    (case_id, proposal_version, action, destination_id, decision,
                     actor_id, tenant_id, decision_scope, decision_channel, decided_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_id, proposal_version) DO NOTHING
                """,
                (
                    case_id,
                    decision.proposal_version,
                    decision.action,
                    decision.destination_id,
                    decision.decision.value,
                    decision.actor_id,
                    decision.tenant_id,
                    decision.scope,
                    decision.channel,
                    decision.decided_at,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM order_resolution_decisions
                WHERE case_id = %s AND proposal_version = %s
                """,
                (case_id, decision.proposal_version),
            ).fetchone()
            if row is None:
                raise Conflict("The decision claim could not be verified.")
            recorded = _decision(row)
            if recorded == decision:
                case = connection.execute(
                    "SELECT status, checkpoint_id, request_id FROM wf_cases WHERE id = %s FOR UPDATE",
                    (case_id,),
                ).fetchone()
                hosted = connection.execute(
                    """
                    SELECT hosted_status, pending_request_id, channel
                    FROM order_resolution_hosted_bindings
                    WHERE case_id = %s FOR UPDATE
                    """,
                    (case_id,),
                ).fetchone()
                existing = connection.execute(
                    "SELECT decision, actor_id FROM wf_decisions WHERE case_id = %s",
                    (case_id,),
                ).fetchone()
                if existing is None:
                    local_pending = (
                        case is not None
                        and case["status"] == "pending"
                        and bool(case["checkpoint_id"])
                        and bool(case["request_id"])
                    )
                    hosted_pending = (
                        case is not None
                        and case["status"] == "pending"
                        and not case["checkpoint_id"]
                        and hosted is not None
                        and hosted["hosted_status"] == "pending"
                        and case["request_id"] == hosted["pending_request_id"]
                        and hosted["channel"] == decision.channel
                    )
                    if not local_pending and not hosted_pending:
                        raise Conflict("The workflow is not waiting for a decision.")
                    connection.execute(
                        "INSERT INTO wf_decisions (case_id, decision, actor_id) VALUES (%s, %s, %s)",
                        (case_id, decision.decision.value, decision.actor_id),
                    )
                    connection.execute(
                        "UPDATE wf_cases SET status = %s, updated_at = now() WHERE id = %s",
                        (decision.decision.value, case_id),
                    )
                    connection.execute(
                        """
                        INSERT INTO wf_audit (case_id, event, actor_id)
                        VALUES (%s, 'decision_recorded', %s)
                        """,
                        (case_id, decision.actor_id),
                    )
                    if hosted_pending:
                        connection.execute(
                            """
                            UPDATE order_resolution_hosted_bindings
                            SET hosted_status = 'decision-recorded', updated_at = now()
                            WHERE case_id = %s
                            """,
                            (case_id,),
                        )
                elif (
                    existing["decision"] != decision.decision.value
                    or existing["actor_id"] != decision.actor_id
                ):
                    raise Conflict("The workflow decision conflicts with the proposal decision.")
            return recorded

    def audit_authorization_denial(self, case_id: UUID, actor_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO order_resolution_audit
                    (case_id, event, actor_id, reason_code)
                VALUES (%s, 'decision_denied', %s, 'authorization_denied')
                """,
                (case_id, actor_id),
            )

    def claim_hosted_operation(
        self,
        case_id: UUID,
        operation_id: str,
        operation_kind: str,
        request_digest: str,
    ) -> HostedOperationClaim:
        if (
            not operation_id
            or len(operation_id) > 256
            or operation_kind not in ("conversation", "start", "resume")
            or not _DIGEST.fullmatch(request_digest)
        ):
            raise ValueError("The hosted operation claim is invalid.")
        with self.connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO order_resolution_hosted_operations
                    (operation_id, case_id, operation_kind, request_digest, status)
                VALUES (%s, %s, %s, %s, 'pending')
                ON CONFLICT (operation_id) DO NOTHING
                RETURNING operation_id
                """,
                (operation_id, case_id, operation_kind, request_digest),
            ).fetchone()
            row = connection.execute(
                """
                SELECT operation_id, case_id, operation_kind, request_digest,
                    status, remote_id
                FROM order_resolution_hosted_operations
                WHERE operation_id = %s
                """,
                (operation_id,),
            ).fetchone()
        if row is None:
            raise Conflict("The hosted operation claim could not be verified.")
        operation = HostedOperation(**row)
        if (
            operation.case_id != case_id
            or operation.operation_kind != operation_kind
            or operation.request_digest != request_digest
        ):
            raise Conflict("The hosted operation ID is bound to different content.")
        return HostedOperationClaim(operation, acquired=inserted is not None)

    def get_hosted_operation(self, operation_id: str) -> HostedOperation | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT operation_id, case_id, operation_kind, request_digest,
                    status, remote_id
                FROM order_resolution_hosted_operations
                WHERE operation_id = %s
                """,
                (operation_id,),
            ).fetchone()
        return HostedOperation(**row) if row is not None else None

    def update_hosted_operation(
        self,
        operation_id: str,
        request_digest: str,
        status: str,
        remote_id: str | None,
    ) -> HostedOperation:
        if status not in ("pending", "acknowledged", "rejected", "unknown"):
            raise ValueError("The hosted operation status is invalid.")
        if (status == "acknowledged") != bool(remote_id):
            raise ValueError("Only acknowledged operations have a remote ID.")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT operation_id, case_id, operation_kind, request_digest,
                    status, remote_id
                FROM order_resolution_hosted_operations
                WHERE operation_id = %s
                FOR UPDATE
                """,
                (operation_id,),
            ).fetchone()
            if row is None or row["request_digest"] != request_digest:
                raise Conflict("The hosted operation claim is missing or conflicts.")
            current = HostedOperation(**row)
            if current.status == "acknowledged":
                if current.status == status and current.remote_id == remote_id:
                    return current
                raise Conflict("An acknowledged hosted operation cannot change outcome.")
            connection.execute(
                """
                UPDATE order_resolution_hosted_operations
                SET status = %s, remote_id = %s, updated_at = now()
                WHERE operation_id = %s
                """,
                (status, remote_id, operation_id),
            )
        operation = self.get_hosted_operation(operation_id)
        if operation is None:
            raise Conflict("The hosted operation update could not be verified.")
        return operation

    @staticmethod
    def _hosted_value(value: str, label: str) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 512
            or any(ord(character) < 0x20 for character in value)
        ):
            raise ValueError(f"{label} is invalid.")
        return value

    def bind_hosted_principal(
        self,
        case_id: UUID,
        principal: Principal,
        *,
        conversation_id: str,
        principal_kind: str,
    ) -> None:
        conversation_id = self._hosted_value(conversation_id, "Hosted conversation identity")
        if principal_kind != "owner":
            raise ValueError("The hosted principal kind is invalid.")
        scopes = sorted(principal.scopes)
        roles = sorted(principal.roles)
        with self.connect() as connection:
            case_row = connection.execute(_CASE_FOR_UPDATE, (case_id,)).fetchone()
            if case_row is None:
                raise NotFound("The case was not found.")
            case = _case(case_row)
            if not (
                principal.tenant_id == case.tenant_id
                and principal.subject == case.owner_id
                and "workflow.read" in principal.scopes
            ):
                raise AccessDenied("The hosted owner is not authorized for the case.")
            row = connection.execute(
                """
                SELECT * FROM order_resolution_hosted_bindings
                WHERE case_id = %s FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO order_resolution_hosted_bindings
                        (case_id, caller_id, session_id, conversation_id,
                         tenant_id, subject_id, scopes, roles, principal_kind, channel)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        case_id,
                        None,
                        None,
                        conversation_id,
                        principal.tenant_id,
                        principal.subject,
                        Jsonb(scopes),
                        Jsonb(roles),
                        principal_kind,
                        HOSTED_CHANNEL,
                    ),
                )
                return
            current = (
                row["tenant_id"],
                row["subject_id"],
                sorted(row["scopes"]),
                sorted(row["roles"]),
                row["principal_kind"],
            )
            requested = (
                principal.tenant_id,
                principal.subject,
                scopes,
                roles,
                principal_kind,
            )
            if (
                row["conversation_id"],
                row["channel"],
            ) == (conversation_id, HOSTED_CHANNEL) and current == requested:
                return
            raise Conflict("The hosted owner binding cannot change identity.")

    def record_hosted_platform_binding(
        self,
        case_id: UUID,
        *,
        conversation_id: str,
        caller_id: str,
        session_id: str,
    ) -> None:
        conversation_id = self._hosted_value(conversation_id, "Hosted conversation identity")
        caller_id = self._hosted_value(caller_id, "Hosted caller identity")
        session_id = self._hosted_value(session_id, "Hosted session identity")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT conversation_id, caller_id, session_id
                FROM order_resolution_hosted_bindings
                WHERE case_id = %s FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if row is None or row["conversation_id"] != conversation_id:
                raise AccessDenied("The hosted platform binding is not authorized.")
            connection.execute(
                """
                UPDATE order_resolution_hosted_bindings
                SET caller_id = %s, session_id = %s, updated_at = now()
                WHERE case_id = %s
                """,
                (caller_id, session_id, case_id),
            )

    def acceptance_binding(self, case_id: UUID) -> dict[str, str]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT conversation_id, session_id
                FROM order_resolution_hosted_bindings
                WHERE case_id = %s
                """,
                (case_id,),
            ).fetchone()
        if row is None or not row["session_id"]:
            raise NotFound("The hosted platform binding is not available.")
        return {
            "conversation_id": row["conversation_id"],
            "session_id": row["session_id"],
        }

    def acceptance_snapshot(self, case_id: UUID) -> dict[str, object]:
        case = self.get(case_id)
        try:
            proposal = self.get_current_proposal(str(case_id))
        except (Conflict, NotFound):
            proposal = None
        proposal_payload = case.payload.get("proposal")
        if not isinstance(proposal_payload, dict):
            proposal_payload = {}
        with self.connect() as connection:
            counts = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM order_resolution_decisions
                     WHERE case_id = %s AND decision = 'approved') AS approved,
                    (SELECT count(*) FROM order_resolution_decisions
                     WHERE case_id = %s AND decision = 'rejected') AS rejected,
                    (SELECT count(*) FROM order_resolution_effects
                     WHERE case_id = %s) AS claims,
                    (SELECT count(*)
                     FROM order_resolution_synthetic_effects s
                     JOIN order_resolution_effects e ON e.effect_key = s.effect_key
                     WHERE e.case_id = %s) AS effects,
                    (SELECT count(*) FROM wf_audit
                     WHERE case_id = %s
                       AND event IN (
                           'workflow_finished',
                           'hosted_workflow_finished',
                           'resolution_failed'
                       )) AS terminal,
                    (SELECT count(*) FROM order_resolution_audit
                     WHERE case_id = %s AND event = 'decision_denied') AS denials
                """,
                (case_id, case_id, case_id, case_id, case_id, case_id),
            ).fetchone()
            actions = connection.execute(
                """
                SELECT action, amount::text, currency
                FROM order_resolution_actions
                WHERE case_id = %s
                ORDER BY created_at
                """,
                (case_id,),
            ).fetchall()
        return {
            "status": case.status,
            "decision": case.decision,
            "proposal": (
                {
                    "version": proposal.proposal_version,
                    "action": proposal.action,
                    "destination_id": proposal.destination_id,
                    "approval_required": proposal.approval_required,
                    "amount": proposal_payload.get("amount"),
                    "currency": proposal_payload.get("currency"),
                }
                if proposal is not None
                else None
            ),
            "counts": {name: int(counts[name]) for name in counts.keys()},
            "verified_actions": [
                {
                    "type": row["action"],
                    **(
                        {"amount": row["amount"], "currency": row["currency"]}
                        if row["amount"] is not None
                        else {"quantity": 1}
                    ),
                }
                for row in actions
            ],
        }

    def bind_hosted_resume_authority(
        self,
        case_id: UUID,
        principal: Principal,
        *,
        conversation_id: str,
        channel: str,
        decision_command: DecisionCommand,
    ) -> None:
        conversation_id = self._hosted_value(conversation_id, "Hosted conversation identity")
        if channel != HOSTED_CHANNEL or decision_command.channel != HOSTED_CHANNEL:
            raise AccessDenied("The hosted decision channel is not authorized.")
        scopes = sorted(principal.scopes)
        roles = sorted(principal.roles)
        with self.connect() as connection:
            case_row = connection.execute(_CASE_FOR_UPDATE, (case_id,)).fetchone()
            if case_row is None:
                raise NotFound("The case was not found.")
            case = _case(case_row)
            if not (
                principal.tenant_id == case.tenant_id
                and principal.subject == case.reviewer_id
                and principal.subject != case.owner_id
                and "workflow.approve" in principal.scopes
                and "Workflow.Approver" in principal.roles
                and case.checkpoint_id is None
                and case.request_id == decision_command.handle
            ):
                raise AccessDenied("The hosted reviewer is not authorized for the case.")
            row = connection.execute(
                """
                SELECT * FROM order_resolution_hosted_bindings
                WHERE case_id = %s FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                raise NotFound("The hosted owner binding was not found.")
            if (
                row["conversation_id"],
                row["channel"],
            ) != (conversation_id, channel):
                raise AccessDenied("The case is bound to a different hosted conversation.")
            proposal_row = connection.execute(
                """
                SELECT * FROM order_resolution_proposals
                WHERE case_id = %s AND is_current
                FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if proposal_row is None:
                raise Conflict("The current proposal was not found.")
            proposal = _proposal(proposal_row)
            handle_digest = hashlib.sha256(decision_command.handle.encode("utf-8")).hexdigest()
            command_matches = not (
                decision_command.case_id != str(case_id)
                or decision_command.proposal_version != proposal.proposal_version
                or decision_command.action != proposal.action
                or decision_command.destination_id != proposal.destination_id
                or decision_command.scope != "workflow.approve"
                or decision_command.channel != proposal.decision_channel
                or proposal.decision_handle_digest != handle_digest
            )
            requested = (
                principal.tenant_id,
                principal.subject,
                scopes,
                roles,
                "reviewer",
            )
            current = (
                row["tenant_id"],
                row["subject_id"],
                sorted(row["scopes"]),
                sorted(row["roles"]),
                row["principal_kind"],
            )
            if case.status in ("approved", "rejected", "completed"):
                intent = connection.execute(
                    """
                    SELECT proposal_version, action, destination_id, handle_digest,
                        decision, actor_id, tenant_id, decision_scope, decision_channel
                    FROM order_resolution_hosted_decision_intents
                    WHERE case_id = %s
                    """,
                    (case_id,),
                ).fetchone()
                decision_row = connection.execute(
                    """
                    SELECT * FROM order_resolution_decisions
                    WHERE case_id = %s AND proposal_version = %s
                    """,
                    (case_id, decision_command.proposal_version),
                ).fetchone()
                decision = _decision(decision_row) if decision_row is not None else None
                if (
                    not command_matches
                    or current != requested
                    or intent is None
                    or decision is None
                    or intent["proposal_version"] != decision_command.proposal_version
                    or intent["action"] != decision_command.action
                    or intent["destination_id"] != decision_command.destination_id
                    or intent["handle_digest"] != handle_digest
                    or intent["decision"] != decision_command.decision.value
                    or intent["actor_id"] != principal.subject
                    or intent["tenant_id"] != principal.tenant_id
                    or intent["decision_scope"] != decision_command.scope
                    or intent["decision_channel"] != decision_command.channel
                    or decision.proposal_version != decision_command.proposal_version
                    or decision.action != decision_command.action
                    or decision.destination_id != decision_command.destination_id
                    or decision.decision != decision_command.decision
                    or decision.actor_id != principal.subject
                    or decision.tenant_id != principal.tenant_id
                    or decision.scope != decision_command.scope
                    or decision.channel != decision_command.channel
                ):
                    raise Conflict(
                        "The hosted decision replay conflicts with the authoritative decision."
                    )
                return
            if (
                case.status != "pending"
                or not command_matches
                or proposal.decision_expires_at is None
                or datetime.now(timezone.utc) >= proposal.decision_expires_at
            ):
                raise AccessDenied("The hosted decision does not match the current proposal.")
            intent = (
                case_id,
                decision_command.proposal_version,
                decision_command.action,
                decision_command.destination_id,
                handle_digest,
                decision_command.decision.value,
                principal.subject,
                principal.tenant_id,
                decision_command.scope,
                decision_command.channel,
            )
            connection.execute(
                """
                INSERT INTO order_resolution_hosted_decision_intents
                    (case_id, proposal_version, action, destination_id, handle_digest,
                     decision, actor_id, tenant_id, decision_scope, decision_channel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_id) DO NOTHING
                """,
                intent,
            )
            stored_intent = connection.execute(
                """
                SELECT case_id, proposal_version, action, destination_id, handle_digest,
                    decision, actor_id, tenant_id, decision_scope, decision_channel
                FROM order_resolution_hosted_decision_intents
                WHERE case_id = %s
                """,
                (case_id,),
            ).fetchone()
            if stored_intent is None or tuple(stored_intent.values()) != intent:
                raise Conflict("The hosted decision intent conflicts with an existing intent.")
            if current == requested:
                return
            if row["principal_kind"] != "owner":
                raise Conflict("The hosted reviewer binding cannot change identity.")
            connection.execute(
                """
                UPDATE order_resolution_hosted_bindings
                SET tenant_id = %s, subject_id = %s,
                    scopes = %s, roles = %s, principal_kind = 'reviewer',
                    updated_at = now()
                WHERE case_id = %s
                """,
                (
                    principal.tenant_id,
                    principal.subject,
                    Jsonb(scopes),
                    Jsonb(roles),
                    case_id,
                ),
            )

    def load_hosted_binding(self, case_id: UUID) -> HostedConversationBinding:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT conversation_id
                FROM order_resolution_hosted_bindings
                WHERE case_id = %s
                """,
                (case_id,),
            ).fetchone()
        if row is None:
            raise NotFound("The hosted conversation binding was not found.")
        return HostedConversationBinding(conversation_id=row["conversation_id"])

    def authorize_hosted_binding(
        self,
        case_id: UUID,
        *,
        conversation_id: str,
        channel: str,
        principal_kind: str,
    ) -> Principal:
        conversation_id = self._hosted_value(conversation_id, "Hosted conversation identity")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT conversation_id, channel, principal_kind,
                    tenant_id, subject_id, scopes, roles
                FROM order_resolution_hosted_bindings
                WHERE case_id = %s
                FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                raise NotFound("The hosted request binding was not found.")
            if (
                row["conversation_id"],
                row["channel"],
                row["principal_kind"],
            ) != (conversation_id, channel, principal_kind):
                raise AccessDenied("The hosted request binding is not authorized.")
            return Principal(
                row["tenant_id"],
                row["subject_id"],
                frozenset(row["scopes"]),
                frozenset(row["roles"]),
            )

    def resolve_hosted_start_principal(
        self,
        case_id: UUID,
        *,
        conversation_id: str,
        channel: str,
    ) -> Principal:
        return self.authorize_hosted_binding(
            case_id,
            conversation_id=conversation_id,
            channel=channel,
            principal_kind="owner",
        )

    def authorize_hosted_resume(
        self,
        case_id: UUID,
        *,
        conversation_id: str,
        channel: str,
    ) -> Principal:
        return self.authorize_hosted_binding(
            case_id,
            conversation_id=conversation_id,
            channel=channel,
            principal_kind="reviewer",
        )

    def prepare_hosted_approval(
        self,
        case_id: UUID,
        candidate_request_id: str,
        *,
        channel: str,
    ) -> Proposal:
        request_id = self._hosted_value(candidate_request_id, "Hosted request identity")
        if channel != HOSTED_CHANNEL:
            raise Conflict("The hosted request channel is not authorized.")
        with self.connect() as connection:
            case = connection.execute(
                """
                SELECT status, checkpoint_id, request_id
                FROM wf_cases WHERE id = %s FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            binding = connection.execute(
                """
                SELECT caller_id, session_id, conversation_id, channel,
                    hosted_status, pending_request_id
                FROM order_resolution_hosted_bindings
                WHERE case_id = %s FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if binding is None or binding["channel"] != channel:
                raise Conflict("The hosted pending request binding is not authorized.")
            if (
                case is not None
                and case["status"] == "pending"
                and case["checkpoint_id"] is None
                and case["request_id"] == request_id
                and binding["hosted_status"] == "pending"
                and binding["pending_request_id"] == request_id
            ):
                return self.get_current_proposal(str(case_id))
            if (
                case is None
                or case["status"] != "created"
                or case["checkpoint_id"] is not None
                or case["request_id"] is not None
                or binding["hosted_status"] != "bound"
                or binding["pending_request_id"] is not None
            ):
                raise Conflict("The hosted workflow already has a pending request.")
            proposal = connection.execute(
                """
                SELECT approval_required FROM order_resolution_proposals
                WHERE case_id = %s AND is_current FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if proposal is None or not proposal["approval_required"]:
                raise Conflict("The hosted workflow does not require approval.")
            connection.execute(
                """
                UPDATE wf_cases SET status = 'pending', request_id = %s,
                    checkpoint_id = NULL, failure_code = NULL, updated_at = now()
                WHERE id = %s
                """,
                (request_id, case_id),
            )
            connection.execute(
                """
                UPDATE order_resolution_hosted_bindings
                SET hosted_status = 'pending', pending_request_id = %s,
                    updated_at = now()
                WHERE case_id = %s
                """,
                (request_id, case_id),
            )
            connection.execute(
                """
                INSERT INTO wf_audit (case_id, event)
                VALUES (%s, 'hosted_request_saved')
                """,
                (case_id,),
            )
        return self.bind_decision_handle(case_id, request_id, channel=channel)

    def claim_hosted_decision(self, decision: DecisionRecord) -> DecisionRecord:
        case_id = UUID(decision.case_id)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT c.status, c.checkpoint_id, c.request_id,
                    b.hosted_status, b.pending_request_id, b.channel,
                    i.proposal_version, i.action, i.destination_id, i.decision,
                    i.actor_id, i.tenant_id, i.decision_scope, i.decision_channel
                FROM wf_cases AS c
                JOIN order_resolution_hosted_bindings AS b ON b.case_id = c.id
                JOIN order_resolution_hosted_decision_intents AS i ON i.case_id = c.id
                WHERE c.id = %s
                """,
                (case_id,),
            ).fetchone()
        if (
            row is None
            or row["checkpoint_id"] is not None
            or not row["request_id"]
            or row["request_id"] != row["pending_request_id"]
            or row["channel"] != decision.channel
            or row["proposal_version"] != decision.proposal_version
            or row["action"] != decision.action
            or row["destination_id"] != decision.destination_id
            or row["decision"] != decision.decision.value
            or row["actor_id"] != decision.actor_id
            or row["tenant_id"] != decision.tenant_id
            or row["decision_scope"] != decision.scope
            or row["decision_channel"] != decision.channel
            or (row["status"] == "pending" and row["hosted_status"] != "pending")
            or (
                row["status"] in ("approved", "rejected")
                and row["hosted_status"] != "decision-recorded"
            )
            or row["status"] not in ("pending", "approved", "rejected")
        ):
            raise Conflict("The hosted workflow is not waiting for this decision.")
        return self.claim_decision(decision)

    def finish_hosted(self, case_id: UUID) -> None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT c.status, c.execution_complete, c.terminal_checkpoint_id,
                    d.decision, b.hosted_status, b.pending_request_id
                FROM wf_cases AS c
                LEFT JOIN wf_decisions AS d ON d.case_id = c.id
                JOIN order_resolution_hosted_bindings AS b ON b.case_id = c.id
                WHERE c.id = %s
                FOR UPDATE OF c, b
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                raise Conflict("The hosted workflow binding is missing.")
            if row["decision"] is None:
                outcome = "automatic"
            else:
                outcome = row["decision"]
            expected_status = "completed" if outcome != "rejected" else "rejected"
            if (
                row["status"] != expected_status
                or row["decision"] not in (None, "approved", "rejected")
                or row["terminal_checkpoint_id"] is not None
            ):
                raise Conflict("The hosted workflow outcome conflicts with business state.")
            if row["execution_complete"]:
                if row["hosted_status"] != "completed":
                    raise Conflict("The hosted completion state is inconsistent.")
                return
            expected_hosted_status = "bound" if outcome == "automatic" else "decision-recorded"
            if row["hosted_status"] != expected_hosted_status:
                raise Conflict("The hosted workflow is not ready to complete.")
            connection.execute(
                """
                UPDATE wf_cases SET execution_complete = TRUE, failure_code = NULL,
                    updated_at = now() WHERE id = %s
                """,
                (case_id,),
            )
            connection.execute(
                """
                UPDATE order_resolution_hosted_bindings
                SET hosted_status = 'completed', updated_at = now()
                WHERE case_id = %s
                """,
                (case_id,),
            )
            connection.execute(
                """
                INSERT INTO wf_audit (case_id, event)
                VALUES (%s, 'hosted_workflow_finished')
                """,
                (case_id,),
            )

    def claim_effect(self, request: EffectRequest) -> EffectLedgerRecord:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO order_resolution_effects
                    (case_id, proposal_version, action, destination_id, effect_key,
                     request_digest, request_body, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'claimed')
                ON CONFLICT DO NOTHING
                """,
                (
                    UUID(request.identity.case_id),
                    request.identity.proposal_version,
                    request.identity.action,
                    request.identity.destination_id,
                    request.key,
                    request.digest,
                    request.body,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM order_resolution_effects
                WHERE case_id = %s AND proposal_version = %s
                    AND action = %s AND destination_id = %s
                """,
                (
                    UUID(request.identity.case_id),
                    request.identity.proposal_version,
                    request.identity.action,
                    request.identity.destination_id,
                ),
            ).fetchone()
        if row is None:
            raise Conflict("The effect claim could not be verified.")
        return _effect(row)

    def mark_effect_unknown(self, request: EffectRequest) -> None:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE order_resolution_effects
                SET status = CASE WHEN status = 'verified' THEN status ELSE 'unknown' END,
                    updated_at = now()
                WHERE case_id = %s AND proposal_version = %s AND action = %s
                    AND destination_id = %s AND effect_key = %s
                    AND request_digest = %s AND request_body = %s
                """,
                (
                    UUID(request.identity.case_id),
                    request.identity.proposal_version,
                    request.identity.action,
                    request.identity.destination_id,
                    request.key,
                    request.digest,
                    request.body,
                ),
            )
            if result.rowcount != 1:
                raise Conflict("The unknown effect outcome conflicts with the ledger.")

    def mark_effect_verified(self, request: EffectRequest, result_digest: str) -> None:
        if not _DIGEST.fullmatch(result_digest):
            raise Conflict("The effect result digest is invalid.")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM order_resolution_effects
                WHERE case_id = %s AND proposal_version = %s AND action = %s
                    AND destination_id = %s
                FOR UPDATE
                """,
                (
                    UUID(request.identity.case_id),
                    request.identity.proposal_version,
                    request.identity.action,
                    request.identity.destination_id,
                ),
            ).fetchone()
            if row is None or _effect(row).request != request:
                raise Conflict("The verified effect conflicts with the ledger.")
            if row["status"] == "verified" and row["result_digest"] != result_digest:
                raise Conflict("A different effect result is already verified.")
            connection.execute(
                """
                UPDATE order_resolution_effects
                SET status = 'verified', result_digest = %s, updated_at = now()
                WHERE case_id = %s AND proposal_version = %s AND action = %s
                    AND destination_id = %s
                """,
                (
                    result_digest,
                    UUID(request.identity.case_id),
                    request.identity.proposal_version,
                    request.identity.action,
                    request.identity.destination_id,
                ),
            )

    def fail_resolution(self, case_id: UUID, code: str) -> None:
        if code not in (
            "policy_evidence_missing",
            "policy_evidence_conflict",
            "policy_evidence_invalid",
        ):
            raise ValueError("Unknown Order Resolution failure code.")
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE wf_cases SET status = 'failed', execution_complete = TRUE,
                    failure_code = %s, updated_at = now()
                WHERE id = %s AND status = 'created'
                """,
                (code, case_id),
            )
            if result.rowcount != 1:
                raise Conflict("The record is not ready for resolution failure.")
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'resolution_failed')",
                (case_id,),
            )

    def _apply(self, case_id: UUID, action: TransactionalAction, *, automatic: bool) -> None:
        with self.connect() as connection:
            row = connection.execute(_CASE_FOR_UPDATE, (case_id,)).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            case = _case(row)
            proposal = self.get_current_proposal(str(case_id))
            ledger = connection.execute(
                "SELECT action_key FROM wf_action_ledger WHERE case_id = %s", (case_id,)
            ).fetchone()
            if ledger:
                expected_decision = None if automatic else "approved"
                if case.status != "completed" or case.decision != expected_decision:
                    raise Conflict("The action ledger and record state are inconsistent.")
                return
            if automatic:
                if (
                    proposal.approval_required
                    or case.status not in ("created", "pending")
                    or case.decision is not None
                ):
                    raise Conflict("The record is not ready for automatic resolution.")
            elif case.decision != "approved" or case.status not in (
                "approved",
                "failed",
            ):
                raise Conflict("The record is not ready for its approved action.")
            try:
                action.apply(connection, case)
            except Exception as exc:
                raise ActionError("The configured action failed.") from exc
            action_key = EffectIdentity.from_proposal(proposal).key
            connection.execute(
                "INSERT INTO wf_action_ledger (case_id, action_key) VALUES (%s, %s)",
                (case_id, action_key),
            )
            connection.execute(
                """
                UPDATE wf_cases SET status = 'completed', failure_code = NULL, updated_at = now()
                WHERE id = %s
                """,
                (case_id,),
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, %s)",
                (
                    case_id,
                    "automatic_action_applied" if automatic else "action_applied",
                ),
            )

    def apply_automatic(self, case_id: UUID, action: TransactionalAction) -> None:
        self._apply(case_id, action, automatic=True)

    def apply_once(self, case_id: UUID, approved: bool, action: TransactionalAction) -> None:
        if not approved:
            case = self.get(case_id)
            if case.decision != "rejected" or case.status != "rejected":
                raise Conflict("The rejected record has an inconsistent state.")
            return
        self._apply(case_id, action, automatic=False)

    def finish_automatic(self, case_id: UUID, terminal_checkpoint_id: str) -> None:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE wf_cases SET execution_complete = TRUE, terminal_checkpoint_id = %s,
                    failure_code = NULL, updated_at = now()
                WHERE id = %s AND status = 'completed'
                    AND NOT EXISTS (SELECT 1 FROM wf_decisions WHERE case_id = %s)
                """,
                (terminal_checkpoint_id, case_id, case_id),
            )
            if result.rowcount != 1:
                raise Conflict(
                    "The automatic workflow finished without a matching business outcome."
                )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'workflow_finished')",
                (case_id,),
            )


class PostgresSyntheticDestination:
    """Synthetic downstream with durable atomic key/digest binding."""

    def __init__(self, store: OrderResolutionStore):
        self.store = store
        self.identity = SYNTHETIC_TOOL_IDENTITY
        self.timeouts: list[float] = []
        self.force_unknown = False
        self.timeout_after_send_once = False

    @staticmethod
    def _milliseconds(timeout_seconds: float) -> int:
        if timeout_seconds <= 0:
            raise TimeoutError("The downstream deadline expired.")
        return max(1, int(timeout_seconds * 1000))

    def observe(self, request: EffectRequest, *, timeout_seconds: float) -> Observation:
        self.timeouts.append(timeout_seconds)
        if self.force_unknown:
            return Observation.UNKNOWN
        with self.store.connect() as connection:
            milliseconds = self._milliseconds(timeout_seconds)
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(milliseconds),),
            )
            connection.execute(
                "SELECT set_config('lock_timeout', %s, true)",
                (str(milliseconds),),
            )
            row = connection.execute(
                """
                SELECT request_digest, request_body, result_digest
                FROM order_resolution_synthetic_effects
                WHERE effect_key = %s
                """,
                (request.key,),
            ).fetchone()
        if row is None:
            return Observation.ABSENT
        if row["request_digest"] != request.digest or bytes(row["request_body"]) != request.body:
            return Observation.CONFLICT
        return (
            Observation.APPLIED if row["result_digest"] == request.digest else Observation.UNKNOWN
        )

    def send(self, request: EffectRequest, *, timeout_seconds: float) -> None:
        self.timeouts.append(timeout_seconds)
        if hashlib.sha256(request.body).hexdigest() != request.digest:
            raise Conflict("The synthetic downstream request digest is invalid.")
        with self.store.connect() as connection:
            milliseconds = self._milliseconds(timeout_seconds)
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(milliseconds),),
            )
            connection.execute(
                "SELECT set_config('lock_timeout', %s, true)",
                (str(milliseconds),),
            )
            connection.execute(
                """
                INSERT INTO order_resolution_synthetic_effects
                    (effect_key, request_digest, request_body, result_digest)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (effect_key) DO NOTHING
                """,
                (request.key, request.digest, request.body, request.digest),
            )
            row = connection.execute(
                """
                SELECT request_digest, request_body, result_digest
                FROM order_resolution_synthetic_effects
                WHERE effect_key = %s
                """,
                (request.key,),
            ).fetchone()
            if (
                row is None
                or row["request_digest"] != request.digest
                or bytes(row["request_body"]) != request.body
                or row["result_digest"] != request.digest
            ):
                raise Conflict("The synthetic downstream key has conflicting content.")
            connection.commit()
        if self.timeout_after_send_once:
            self.timeout_after_send_once = False
            raise TimeoutError("The synthetic effect applied before acknowledgment timed out.")
