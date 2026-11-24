from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain.errors import InvalidInput
from app.infrastructure.telemetry import current_request_id
from app.order_resolution.persistence import HostedOperation, OrderResolutionStore


class PostgresOperationJournal:
    """Adapt application-owned PostgreSQL claims to Agent A's exact client types."""

    def __init__(
        self,
        store: OrderResolutionStore,
        *,
        record_type: type | None = None,
        claim_type: type | None = None,
        status_type: type | None = None,
    ) -> None:
        if record_type is None or claim_type is None or status_type is None:
            from order_resolution_hosted.client import (
                OperationClaim,
                OperationRecord,
                OperationStatus,
            )

            record_type = OperationRecord
            claim_type = OperationClaim
            status_type = OperationStatus
        self._store = store
        self._record_type = record_type
        self._claim_type = claim_type
        self._status_type = status_type

    @staticmethod
    def _identity(operation_id: str) -> tuple[UUID, str]:
        parts = operation_id.split(":")
        if len(parts) < 3 or parts[0] != "case":
            raise InvalidInput("Hosted operation IDs must be case-bound.")
        try:
            case_id = UUID(parts[1])
        except ValueError as exc:
            raise InvalidInput("Hosted operation IDs must contain a case UUID.") from exc
        operation_kind = {
            "conversation": "conversation",
            "start": "start",
            "decision": "resume",
        }.get(parts[2])
        if operation_kind is None:
            raise InvalidInput("The hosted operation kind is invalid.")
        return case_id, operation_kind

    def _record(self, operation: HostedOperation) -> Any:
        return self._record_type(
            operation_id=operation.operation_id,
            request_digest=operation.request_digest,
            status=self._status_type(operation.status),
            remote_id=operation.remote_id,
        )

    def claim(self, operation_id: str, request_digest: str) -> Any:
        case_id, operation_kind = self._identity(operation_id)
        claim = self._store.claim_hosted_operation(
            case_id,
            operation_id,
            operation_kind,
            request_digest,
            request_id=current_request_id() if operation_kind == "start" else None,
        )
        return self._claim_type(
            record=self._record(claim.record),
            acquired=claim.acquired,
        )

    def update(self, record: Any) -> Any:
        status = getattr(record.status, "value", None)
        if not isinstance(status, str):
            raise TypeError("The hosted operation status type is invalid.")
        operation = self._store.update_hosted_operation(
            record.operation_id,
            record.request_digest,
            status,
            record.remote_id,
        )
        return self._record(operation)

    def get(self, operation_id: str) -> Any | None:
        operation = self._store.get_hosted_operation(operation_id)
        return self._record(operation) if operation is not None else None
