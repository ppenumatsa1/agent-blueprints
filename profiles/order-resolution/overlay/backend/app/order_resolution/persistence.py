import hashlib
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from psycopg.types.json import Jsonb

from app.domain.errors import ActionError, Conflict, NotFound
from app.domain.models import Principal, TransactionalAction
from app.infrastructure.store import PostgresStore, _case
from app.order_resolution.durability import (
    Decision,
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
                existing = connection.execute(
                    "SELECT decision, actor_id FROM wf_decisions WHERE case_id = %s",
                    (case_id,),
                ).fetchone()
                if existing is None:
                    if (
                        case is None
                        or case["status"] != "pending"
                        or not case["checkpoint_id"]
                        or not case["request_id"]
                    ):
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
            if automatic:
                if proposal.approval_required or case.status != "created":
                    raise Conflict("The record is not ready for automatic resolution.")
            elif case.decision != "approved" or case.status not in ("approved", "failed"):
                raise Conflict("The record is not ready for its approved action.")
            ledger = connection.execute(
                "SELECT action_key FROM wf_action_ledger WHERE case_id = %s", (case_id,)
            ).fetchone()
            if ledger:
                if case.status != "completed":
                    raise Conflict("The action ledger and record state are inconsistent.")
                return
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
                (case_id, "automatic_action_applied" if automatic else "action_applied"),
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
