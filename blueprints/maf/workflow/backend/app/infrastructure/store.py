from contextlib import contextmanager
from threading import BoundedSemaphore
from typing import Iterator
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.config import Settings
from app.domain.errors import ActionError, Conflict, NotFound
from app.domain.models import (
    Case,
    Decision,
    DurableActivity,
    HistoryCandidate,
    Principal,
    TransactionalAction,
)
from app.infrastructure.database import (
    BoundedConnectionPool,
    DatabaseConnectionOptions,
    DatabaseConnector,
    TokenProvider,
)
from app.infrastructure.telemetry import instrumented
from app.usecases.history import CursorPosition


_CASE_QUERY = """
    SELECT c.*, d.decision
    FROM wf_cases AS c
    LEFT JOIN wf_decisions AS d ON d.case_id = c.id
    WHERE c.id = %s
"""
_AUDIT_ACTIVITY_TYPES = {
    "created": "created",
    "checkpoint_saved": "review_requested",
    "hosted_request_saved": "request_recorded",
    "decision_recorded": "decision_recorded",
    "action_applied": "action_applied",
    "automatic_action_applied": "action_applied",
    "action_failed": "action_failed",
    "workflow_finished": "workflow_finished",
    "hosted_workflow_finished": "workflow_finished",
    "recovery_failed": "recovery_failed",
    "resolution_failed": "workflow_failed",
    "hosted_response_failed": "workflow_failed",
}
MAX_CONCURRENT_POLL_READS = 4
# Local workflow execution holds an advisory-lock connection while borrowing another.
BUSINESS_POOL_RESERVATION = 2


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

    def __init__(
        self,
        dsn: str,
        *,
        auth_mode: str = "password",
        password: str | None = None,
        managed_identity_client_id: str | None = None,
        tls_mode: str | None = None,
        tls_root_cert: str | None = None,
        pool_min_size: int = 1,
        pool_max_size: int = 8,
        pool_timeout_seconds: float = 5.0,
        connection_max_lifetime_seconds: float = 2700.0,
        token_provider: TokenProvider | None = None,
    ):
        if not dsn:
            raise ValueError("A PostgreSQL connection string is required.")
        self._dsn = dsn
        self._connector = DatabaseConnector(
            DatabaseConnectionOptions(
                dsn,
                auth_mode,
                password,
                managed_identity_client_id,
                tls_mode,
                tls_root_cert,
            ),
            token_provider,
        )
        self._custom_connection = bool(
            auth_mode != "password"
            or password
            or managed_identity_client_id
            or tls_mode
            or tls_root_cert
        )
        self._pool = BoundedConnectionPool(
            self._connector.connect,
            min_size=pool_min_size,
            max_size=pool_max_size,
            timeout_seconds=pool_timeout_seconds,
            max_lifetime_seconds=connection_max_lifetime_seconds,
            open_connection=self._open_connection,
            checkout_failure=self._record_checkout_failure,
        )
        # Preserve reads at the supported minimum, without a two-connection reservation.
        poll_limit = (
            1
            if pool_max_size == 2
            else min(MAX_CONCURRENT_POLL_READS, max(0, pool_max_size - BUSINESS_POOL_RESERVATION))
        )
        self._poll_read_slots = BoundedSemaphore(poll_limit)
        self.telemetry = None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        token_provider: TokenProvider | None = None,
    ):
        return cls(
            settings.database_url,
            auth_mode=settings.database_auth_mode,
            password=settings.database_password,
            managed_identity_client_id=(
                settings.database_managed_identity_client_id
                or settings.api_managed_identity_client_id
            ),
            tls_mode=settings.database_tls_mode,
            tls_root_cert=settings.database_tls_root_cert,
            pool_min_size=settings.database_pool_min_size,
            pool_max_size=settings.database_pool_max_size,
            pool_timeout_seconds=settings.database_pool_timeout_seconds,
            connection_max_lifetime_seconds=(settings.database_connection_max_lifetime_seconds),
            token_provider=token_provider,
        )

    def connect(self):
        return self._pool.connection()

    @contextmanager
    def poll_read(self) -> Iterator[bool]:
        admitted = self._poll_read_slots.acquire(blocking=False)
        try:
            yield admitted
        finally:
            if admitted:
                self._poll_read_slots.release()

    def _open_connection(self, reason: str):
        if self.telemetry is None:
            return self._connector.connect()
        with self.telemetry.operation("database.connection.open") as operation:
            operation.set_attribute("blueprint.database.connection.reason", reason)
            return self._connector.connect()

    def _record_checkout_failure(self, error: BaseException) -> None:
        if self.telemetry is None:
            return
        with self.telemetry.operation("database.pool.checkout") as operation:
            operation.fail(error)

    def initialize(self) -> None:
        from app.infrastructure.migrations import validate

        if self._custom_connection:
            validate(
                self._dsn,
                connect=lambda: self._connector.connect(dict_rows=False),
            )
        else:
            validate(self._dsn)
        self._pool.open()

    def close(self) -> None:
        self._pool.close()

    @instrumented("database.read")
    def get(self, case_id: UUID) -> Case:
        with self.connect() as connection:
            row = connection.execute(_CASE_QUERY, (case_id,)).fetchone()
        if row is None:
            raise NotFound("Record not found.")
        return _case(row)

    async def get_for_activity_stream(self, case_id: UUID) -> Case:
        # A separate cancellable connection cannot exhaust the synchronous API pool.
        async with await self._connector.connect_for_activity_stream() as connection:
            cursor = await connection.execute(_CASE_QUERY, (case_id,))
            row = await cursor.fetchone()
        if row is None:
            raise NotFound("Record not found.")
        return _case(row)

    @instrumented("database.history")
    def list_history(
        self,
        actor: Principal,
        status: str | None,
        cursor: CursorPosition | None,
        limit: int,
    ) -> tuple[list[HistoryCandidate], bool]:
        conditions = [
            "c.tenant_id = %s",
            "(c.owner_id = %s OR c.reviewer_id = %s)",
        ]
        parameters: list[object] = [actor.tenant_id, actor.subject, actor.subject]
        if status is not None:
            conditions.append("c.status = %s")
            parameters.append(status)
        if cursor is not None:
            conditions.append("(c.created_at, c.id) < (%s, %s)")
            parameters.extend((cursor.created_at, cursor.row_id))
        query = f"""
            SELECT c.*, d.decision
            FROM wf_cases AS c
            LEFT JOIN wf_decisions AS d ON d.case_id = c.id
            WHERE {" AND ".join(conditions)}
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT %s
        """
        parameters.append(limit + 1)
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        has_more = len(rows) > limit
        entries = [
            HistoryCandidate(
                case=_case(row),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows[:limit]
        ]
        return entries, has_more

    @instrumented("database.activity")
    def list_activity(
        self,
        actor: Principal,
        case_id: UUID,
        cursor: CursorPosition | None,
        limit: int,
    ) -> tuple[list[DurableActivity], bool]:
        conditions = [
            "c.id = %s",
            "c.tenant_id = %s",
            "(c.owner_id = %s OR c.reviewer_id = %s)",
            "a.event = ANY(%s)",
        ]
        parameters: list[object] = [
            case_id,
            actor.tenant_id,
            actor.subject,
            actor.subject,
            list(_AUDIT_ACTIVITY_TYPES),
        ]
        if cursor is not None:
            conditions.append("(a.created_at, a.id) < (%s, %s)")
            parameters.extend((cursor.created_at, cursor.row_id))
        query = f"""
            SELECT a.id, a.event, a.created_at
            FROM wf_audit AS a
            JOIN wf_cases AS c ON c.id = a.case_id
            WHERE {" AND ".join(conditions)}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT %s
        """
        parameters.append(limit + 1)
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        has_more = len(rows) > limit
        entries = [
            DurableActivity(
                cursor_id=row["id"],
                event_type=_AUDIT_ACTIVITY_TYPES[row["event"]],
                created_at=row["created_at"],
            )
            for row in rows[:limit]
        ]
        return entries, has_more

    @instrumented("database.create")
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
                (
                    case_id,
                    actor.tenant_id,
                    actor.subject,
                    reviewer_id,
                    Jsonb(payload),
                    idempotency_key,
                    input_digest,
                ),
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
        with self.connect() as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s, %s) AS acquired", (first, second)
            ).fetchone()["acquired"]
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

    @instrumented("database.decision")
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
            row = connection.execute(_CASE_QUERY + " FOR UPDATE OF c", (case_id,)).fetchone()
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

    @instrumented("database.finish")
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
                WHERE NOT execution_complete AND (
                    status IN ('created', 'approved', 'rejected', 'completed')
                    OR (status = 'pending' AND failure_code = 'hosted_outcome_unknown')
                )
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
