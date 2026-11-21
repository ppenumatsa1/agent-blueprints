from contextlib import contextmanager
from typing import Iterator
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.domain.errors import ActionError, Conflict, NotFound
from app.domain.models import Case, Decision, Principal, TransactionalAction


_CASE_QUERY = """
    SELECT c.*, d.decision
    FROM wf_cases AS c
    LEFT JOIN wf_decisions AS d ON d.case_id = c.id
    WHERE c.id = %s
"""


def _case(row: dict) -> Case:
    return Case(
        id=row["id"],
        tenant_id=row["tenant_id"],
        owner_id=row["owner_id"],
        reviewer_id=row["reviewer_id"],
        payload=row["payload"],
        status=row["status"],
        decision=row["decision"],
        request_id=row["request_id"],
        checkpoint_id=row["checkpoint_id"],
        terminal_checkpoint_id=row["terminal_checkpoint_id"],
        execution_complete=row["execution_complete"],
        failure_code=row["failure_code"],
    )


class PostgresStore:
    """Application records and transactional effects, not MAF checkpoints."""

    def __init__(self, dsn: str):
        if not dsn:
            raise ValueError("A PostgreSQL connection string is required.")
        self._dsn = dsn

    def connect(self):
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def initialize(self) -> None:
        from app.infrastructure.migrations import validate

        validate(self._dsn)

    def get(self, case_id: UUID) -> Case:
        with self.connect() as connection:
            row = connection.execute(_CASE_QUERY, (case_id,)).fetchone()
        if row is None:
            raise NotFound("Record not found.")
        return _case(row)

    def create(
        self,
        actor: Principal,
        reviewer_id: str,
        payload: dict,
        idempotency_key: str,
        input_digest: str,
    ) -> Case:
        case_id = uuid4()
        with self.connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO wf_cases
                    (id, tenant_id, owner_id, reviewer_id, payload, idempotency_key, input_digest, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'created')
                ON CONFLICT (tenant_id, owner_id, idempotency_key) DO NOTHING
                RETURNING id
                """,
                (case_id, actor.tenant_id, actor.subject, reviewer_id, Jsonb(payload), idempotency_key, input_digest),
            ).fetchone()
            if inserted:
                connection.execute(
                    "INSERT INTO wf_audit (case_id, event, actor_id) VALUES (%s, 'created', %s)",
                    (case_id, actor.subject),
                )
            else:
                existing = connection.execute(
                    """
                    SELECT id, input_digest FROM wf_cases
                    WHERE tenant_id = %s AND owner_id = %s AND idempotency_key = %s
                    """,
                    (actor.tenant_id, actor.subject, idempotency_key),
                ).fetchone()
                if existing is None or existing["input_digest"] != input_digest:
                    raise Conflict("The idempotency key was already used for a different request.")
                case_id = existing["id"]
        return self.get(case_id)

    @contextmanager
    def run_lock(self, case_id: UUID) -> Iterator[None]:
        # A session lock spans both checkpoint writes and independently committed
        # database transactions, and PostgreSQL releases it if the worker dies.
        first = int.from_bytes(case_id.bytes[:4], "big", signed=True)
        second = int.from_bytes(case_id.bytes[4:8], "big", signed=True)
        with psycopg.connect(self._dsn, autocommit=True) as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s, %s)", (first, second)
            ).fetchone()[0]
            if not acquired:
                raise Conflict("The workflow is already being processed.")
            try:
                yield
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s, %s)", (first, second))

    def save_pending(self, case_id: UUID, checkpoint_id: str, request_id: str) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status, checkpoint_id, request_id FROM wf_cases WHERE id = %s FOR UPDATE",
                (case_id,),
            ).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            if row["status"] != "created":
                if row["checkpoint_id"] == checkpoint_id and row["request_id"] == request_id:
                    return
                raise Conflict("The workflow already has a pending request.")
            connection.execute(
                """
                UPDATE wf_cases SET status = 'pending', checkpoint_id = %s, request_id = %s,
                    failure_code = NULL, updated_at = now() WHERE id = %s
                """,
                (checkpoint_id, request_id, case_id),
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'checkpoint_saved')", (case_id,)
            )

    def record_decision(self, case_id: UUID, actor: Principal, decision: Decision) -> Case:
        if decision not in ("approved", "rejected"):
            raise ValueError("Decision must be approved or rejected.")
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM wf_cases WHERE id = %s FOR UPDATE", (case_id,)
            ).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            existing = connection.execute(
                "SELECT decision, actor_id FROM wf_decisions WHERE case_id = %s", (case_id,)
            ).fetchone()
            if existing:
                if existing["decision"] != decision or existing["actor_id"] != actor.subject:
                    raise Conflict("A different decision has already been recorded.")
            else:
                if row["status"] != "pending" or not row["checkpoint_id"] or not row["request_id"]:
                    raise Conflict("The workflow is not waiting for a decision.")
                connection.execute(
                    "INSERT INTO wf_decisions (case_id, decision, actor_id) VALUES (%s, %s, %s)",
                    (case_id, decision, actor.subject),
                )
                connection.execute(
                    "UPDATE wf_cases SET status = %s, updated_at = now() WHERE id = %s",
                    (decision, case_id),
                )
                connection.execute(
                    "INSERT INTO wf_audit (case_id, event, actor_id) VALUES (%s, 'decision_recorded', %s)",
                    (case_id, actor.subject),
                )
        return self.get(case_id)

    def apply_once(self, case_id: UUID, approved: bool, action: TransactionalAction) -> None:
        with self.connect() as connection:
            row = connection.execute(
                _CASE_QUERY + " FOR UPDATE OF c", (case_id,)
            ).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            case = _case(row)
            expected = "approved" if approved else "rejected"
            if case.decision != expected:
                raise Conflict("The workflow response does not match the recorded decision.")
            if not approved:
                if case.status != "rejected":
                    raise Conflict("The rejected record has an inconsistent state.")
                return
            ledger = connection.execute(
                "SELECT action_key FROM wf_action_ledger WHERE case_id = %s", (case_id,)
            ).fetchone()
            if ledger:
                if case.status != "completed":
                    raise Conflict("The action ledger and record state are inconsistent.")
                return
            if case.status not in ("approved", "failed"):
                raise Conflict("The record is not ready for its action.")
            try:
                action.apply(connection, case)
            except Exception as exc:
                raise ActionError("The configured action failed.") from exc
            connection.execute(
                "INSERT INTO wf_action_ledger (case_id, action_key) VALUES (%s, %s)",
                (case_id, f"case:{case_id}:action"),
            )
            connection.execute(
                "UPDATE wf_cases SET status = 'completed', failure_code = NULL, updated_at = now() WHERE id = %s",
                (case_id,),
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'action_applied')", (case_id,)
            )

    def mark_action_failed(self, case_id: UUID) -> None:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE wf_cases SET status = 'failed', failure_code = 'action_failed', updated_at = now()
                WHERE id = %s AND status IN ('approved', 'failed')
                """,
                (case_id,),
            )
            if result.rowcount:
                connection.execute(
                    "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'action_failed')", (case_id,)
                )

    def finish(self, case_id: UUID, terminal_checkpoint_id: str) -> None:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE wf_cases SET execution_complete = TRUE, terminal_checkpoint_id = %s,
                    failure_code = NULL, updated_at = now()
                WHERE id = %s AND status IN ('completed', 'rejected')
                """,
                (terminal_checkpoint_id, case_id),
            )
            if result.rowcount != 1:
                raise Conflict("The workflow finished without a matching business outcome.")
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'workflow_finished')", (case_id,)
            )

    def recoverable(self) -> list[tuple[UUID, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, status FROM wf_cases
                WHERE NOT execution_complete AND status IN ('created', 'approved', 'rejected', 'completed')
                ORDER BY created_at, id
                """
            ).fetchall()
        return [(row["id"], row["status"]) for row in rows]

    def mark_recovery_failed(self, case_id: UUID, code: str) -> None:
        with self.connect() as connection:
            result = connection.execute(
                "UPDATE wf_cases SET failure_code = %s, updated_at = now() WHERE id = %s",
                (code, case_id),
            )
            if result.rowcount != 1:
                raise NotFound("Record not found.")
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'recovery_failed')", (case_id,)
            )
