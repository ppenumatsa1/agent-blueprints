from contextlib import contextmanager
import os
from typing import Iterator
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.config import Settings
from app.domain.errors import ActionError, Conflict, NotFound
from app.domain.models import Case, Decision, Principal, TransactionalAction
from app.infrastructure.database import (
    BoundedConnectionPool,
    DatabaseConnectionOptions,
    DatabaseConnector,
    TokenProvider,
)
from app.infrastructure.telemetry import instrumented


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

    def __init__(
        self,
        dsn: str,
        *,
        auth_mode: str = "password",
        password: str | None = None,
        managed_identity_client_id: str | None = None,
        tls_mode: str | None = None,
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
            ),
            token_provider,
        )
        self._custom_connection = bool(
            auth_mode != "password"
            or password
            or managed_identity_client_id
            or tls_mode
        )
        self._pool = BoundedConnectionPool(
            self._connector.connect,
            min_size=pool_min_size,
            max_size=pool_max_size,
            timeout_seconds=pool_timeout_seconds,
            max_lifetime_seconds=connection_max_lifetime_seconds,
        )
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
            pool_min_size=settings.database_pool_min_size,
            pool_max_size=settings.database_pool_max_size,
            pool_timeout_seconds=settings.database_pool_timeout_seconds,
            connection_max_lifetime_seconds=(
                settings.database_connection_max_lifetime_seconds
            ),
            token_provider=token_provider,
        )

    @classmethod
    def from_database_environment(cls):
        def integer(name: str, default: str) -> int:
            try:
                return int(os.environ.get(name, default))
            except ValueError as exc:
                raise ValueError(f"{name} must be an integer.") from exc

        def number(name: str, default: str) -> float:
            try:
                return float(os.environ.get(name, default))
            except ValueError as exc:
                raise ValueError(f"{name} must be a number.") from exc

        dsn = os.environ.get("DATABASE_URL", "")
        if not dsn:
            raise ValueError("DATABASE_URL is required.")
        return cls(
            dsn,
            auth_mode=os.environ.get("DATABASE_AUTH_MODE", "password"),
            password=os.environ.get("DATABASE_PASSWORD") or None,
            managed_identity_client_id=(
                os.environ.get("DATABASE_MANAGED_IDENTITY_CLIENT_ID")
                or os.environ.get("API_MANAGED_IDENTITY_CLIENT_ID")
                or None
            ),
            tls_mode=os.environ.get("DATABASE_TLS_MODE") or None,
            pool_min_size=integer("DATABASE_POOL_MIN_SIZE", "1"),
            pool_max_size=integer("DATABASE_POOL_MAX_SIZE", "8"),
            pool_timeout_seconds=number("DATABASE_POOL_TIMEOUT_SECONDS", "5"),
            connection_max_lifetime_seconds=number(
                "DATABASE_CONNECTION_MAX_LIFETIME_SECONDS", "2700"
            ),
        )

    @instrumented("database.connect")
    def connect(self):
        return self._pool.connection()

    def initialize(self) -> None:
        from app.infrastructure.migrations import validate

        if self._custom_connection:
            validate(
                self._dsn,
                connect=lambda: self._connector.connect(dict_rows=False),
            )
        else:
            validate(self._dsn)

    def close(self) -> None:
        self._pool.close()

    @instrumented("database.read")
    def get(self, case_id: UUID) -> Case:
        with self.connect() as connection:
            row = connection.execute(_CASE_QUERY, (case_id,)).fetchone()
        if row is None:
            raise NotFound("Record not found.")
        return _case(row)

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

    def claim_hosted_start(self, case_id: UUID, operation_id: str) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status, checkpoint_id, request_id FROM wf_cases WHERE id = %s FOR UPDATE",
                (case_id,),
            ).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            if row["status"] == "created":
                connection.execute(
                    """
                    UPDATE wf_cases SET status = 'pending', checkpoint_id = %s,
                        request_id = %s, failure_code = 'hosted_outcome_unknown',
                        updated_at = now() WHERE id = %s
                    """,
                    (operation_id, operation_id, case_id),
                )
                return
            if (
                row["status"] == "pending"
                and row["checkpoint_id"] == operation_id
                and row["request_id"] == operation_id
            ):
                return
            raise Conflict("The hosted workflow start is already claimed.")

    def confirm_hosted_pending(
        self,
        case_id: UUID,
        operation_id: str,
        execution_id: str,
        request_id: str,
    ) -> None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT status, checkpoint_id, request_id
                FROM wf_cases WHERE id = %s FOR UPDATE
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            if (
                row["status"] == "pending"
                and row["checkpoint_id"] == execution_id
                and row["request_id"] == request_id
            ):
                return
            if (
                row["status"] != "pending"
                or row["checkpoint_id"] != operation_id
                or row["request_id"] != operation_id
            ):
                raise Conflict("The hosted workflow response conflicts with the dispatch claim.")
            connection.execute(
                """
                UPDATE wf_cases SET checkpoint_id = %s, request_id = %s,
                    failure_code = NULL, updated_at = now() WHERE id = %s
                """,
                (execution_id, request_id, case_id),
            )

    def claim_hosted_resume(self, case_id: UUID) -> None:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE wf_cases SET failure_code = 'hosted_outcome_unknown', updated_at = now()
                WHERE id = %s AND status IN ('approved', 'rejected')
                    AND NOT execution_complete
                """,
                (case_id,),
            )
            if result.rowcount != 1:
                raise Conflict("The hosted workflow is not ready to resume.")

    def decision_actor(self, case_id: UUID) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT actor_id FROM wf_decisions WHERE case_id = %s", (case_id,)
            ).fetchone()
        if row is None:
            raise Conflict("The hosted decision actor is missing.")
        return row["actor_id"]

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
