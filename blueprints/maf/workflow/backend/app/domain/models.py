from dataclasses import dataclass
from typing import Any, ContextManager, Literal, Protocol
from uuid import UUID

from psycopg import Connection


Decision = Literal["approved", "rejected"]


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    subject: str
    scopes: frozenset[str]
    roles: frozenset[str]


@dataclass(frozen=True)
class Case:
    id: UUID
    tenant_id: str
    owner_id: str
    reviewer_id: str
    payload: dict[str, Any]
    status: str
    decision: Decision | None
    request_id: str | None
    checkpoint_id: str | None
    terminal_checkpoint_id: str | None
    execution_complete: bool
    failure_code: str | None


class BusinessRules(Protocol):
    def validate(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class AccessPolicy(Protocol):
    def authorize_submission(self, actor: Principal, reviewer_id: str) -> None: ...

    def authorize_read(self, actor: Principal, case: Case) -> None: ...

    def authorize_decision(self, actor: Principal, case: Case) -> None: ...


class TransactionalAction(Protocol):
    def apply(self, connection: Connection, case: Case) -> None:
        """Perform the application-owned action within the supplied transaction."""
        ...


class StateRepository(Protocol):
    def initialize(self) -> None: ...

    def connect(self) -> Connection: ...

    def get(self, case_id: UUID) -> Case: ...

    def create(
        self,
        actor: Principal,
        reviewer_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
        input_digest: str,
    ) -> Case: ...

    def run_lock(self, case_id: UUID) -> ContextManager[None]: ...

    def save_pending(self, case_id: UUID, checkpoint_id: str, request_id: str) -> None: ...

    def record_decision(self, case_id: UUID, actor: Principal, decision: Decision) -> Case: ...

    def apply_once(self, case_id: UUID, approved: bool, action: TransactionalAction) -> None: ...

    def mark_action_failed(self, case_id: UUID) -> None: ...

    def finish(self, case_id: UUID, terminal_checkpoint_id: str) -> None: ...

    def recoverable(self) -> list[tuple[UUID, str]]: ...

    def mark_recovery_failed(self, case_id: UUID, code: str) -> None: ...


class WorkflowHost(Protocol):
    async def start(self, case_id: UUID) -> None: ...

    async def resume(self, case_id: UUID) -> None: ...
