import os
from uuid import UUID

from app.order_resolution.migrations import validate_connection
from app.order_resolution.persistence import (
    HOSTED_CHANNEL,
    HostedOperation,
    OrderResolutionStore,
)


def _caller_value(caller, name: str) -> str:
    value = getattr(caller, name, None)
    if not isinstance(value, str) or not value:
        raise PermissionError("The hosted caller identity is incomplete.")
    return value


class PostgresHostedIdentityBindings:
    """Durable bridge from AgentServer caller context to application authority."""

    def __init__(self, store: OrderResolutionStore):
        self.store = store

    def resolve_principal(self, caller):
        return self.store.resolve_hosted_principal(
            _caller_value(caller, "user_id"),
            _caller_value(caller, "session_id"),
        )

    def bind_start(self, *, case_id: UUID, caller, conversation_id: str) -> None:
        self.store.authorize_hosted_binding(
            case_id,
            caller_id=_caller_value(caller, "user_id"),
            session_id=_caller_value(caller, "session_id"),
            conversation_id=conversation_id,
            channel=HOSTED_CHANNEL,
            principal_kind="owner",
        )

    def authorize_resume(
        self,
        *,
        case_id: UUID,
        caller,
        conversation_id: str,
        channel: str,
    ) -> None:
        self.store.authorize_hosted_binding(
            case_id,
            caller_id=_caller_value(caller, "user_id"),
            session_id=_caller_value(caller, "session_id"),
            conversation_id=conversation_id,
            channel=channel,
            principal_kind="reviewer",
        )

    def save_pending(
        self,
        *,
        case_id: UUID,
        caller,
        conversation_id: str,
        request_id: str,
        channel: str,
    ) -> None:
        self.store.authorize_hosted_binding(
            case_id,
            caller_id=_caller_value(caller, "user_id"),
            session_id=_caller_value(caller, "session_id"),
            conversation_id=conversation_id,
            channel=channel,
            principal_kind="owner",
        )
        self.store.prepare_hosted_approval(case_id, request_id, channel=channel)

    def complete(self, *, case_id: UUID) -> None:
        self.store.finish_hosted(case_id)


def _operation_identity(operation_id: str) -> tuple[UUID, str]:
    parts = operation_id.split(":")
    if len(parts) < 3 or parts[0] != "case":
        raise ValueError("Hosted operation IDs must be case-bound.")
    case_id = UUID(parts[1])
    kind = parts[2]
    operation_kind = (
        "conversation"
        if kind == "conversation"
        else "start"
        if kind == "start"
        else "resume"
        if kind == "decision"
        else None
    )
    if operation_kind is None:
        raise ValueError("The hosted operation kind is invalid.")
    return case_id, operation_kind


class PostgresOperationJournal:
    """Agent A OperationJournal adapter backed by atomic PostgreSQL records."""

    def __init__(self, store: OrderResolutionStore):
        self.store = store

    @staticmethod
    def _record(operation: HostedOperation):
        from order_resolution_hosted.client import OperationRecord, OperationStatus

        return OperationRecord(
            operation.operation_id,
            operation.request_digest,
            OperationStatus(operation.status),
            operation.remote_id,
        )

    def claim(self, operation_id: str, request_digest: str):
        case_id, operation_kind = _operation_identity(operation_id)
        return self._record(
            self.store.claim_hosted_operation(
                case_id,
                operation_id,
                operation_kind,
                request_digest,
            )
        )

    def update(self, record):
        return self._record(
            self.store.update_hosted_operation(
                record.operation_id,
                record.request_digest,
                record.status.value,
                record.remote_id,
            )
        )

    def get(self, operation_id: str):
        operation = self.store.get_hosted_operation(operation_id)
        return self._record(operation) if operation is not None else None


def _store() -> OrderResolutionStore:
    store = OrderResolutionStore.from_database_environment()
    store.initialize()
    with store.connect() as connection:
        validate_connection(connection)
    return store


def build_hosted_identity_bindings() -> PostgresHostedIdentityBindings:
    return PostgresHostedIdentityBindings(_store())


def build_operation_journal() -> PostgresOperationJournal:
    return PostgresOperationJournal(_store())


def required_hosted_environment() -> dict[str, str]:
    return {
        "ORDER_RESOLUTION_HOSTED_IDENTITY_BINDINGS": (
            "app.order_resolution.hosted_bindings:build_hosted_identity_bindings"
        ),
        "ORDER_RESOLUTION_OPERATION_JOURNAL": (
            "app.order_resolution.hosted_bindings:build_operation_journal"
        ),
        "FOUNDRY_PROJECT_ENDPOINT": os.environ.get("FOUNDRY_PROJECT_ENDPOINT", ""),
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": os.environ.get(
            "AZURE_AI_MODEL_DEPLOYMENT_NAME", ""
        ),
    }
