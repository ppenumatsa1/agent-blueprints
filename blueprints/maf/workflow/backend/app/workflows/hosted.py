from uuid import UUID

from app.domain.errors import CheckpointError, HostedWorkflowError
from app.domain.models import StateRepository, TransactionalAction
from app.infrastructure.hosted import (
    HostedResult,
    HostedResume,
    HostedStart,
    HostedWorkflowClient,
)
from app.infrastructure.telemetry import instrumented


class HostedWorkflowHost:
    """Coordinate application state with Agent A without importing its SDK."""

    def __init__(
        self,
        store: StateRepository,
        action: TransactionalAction,
        client: HostedWorkflowClient,
        *,
        telemetry=None,
    ):
        self.store = store
        self.action = action
        self.client = client
        self.telemetry = telemetry

    @staticmethod
    def _start_operation(case_id: UUID) -> str:
        return f"case:{case_id}:start"

    @staticmethod
    def _resume_operation(case_id: UUID, decision: str) -> str:
        return f"case:{case_id}:decision:{decision}"

    def _finish(self, case_id: UUID, result: HostedResult) -> None:
        case = self.store.get(case_id)
        if result.status == "pending":
            bind = getattr(self.store, "bind_decision_handle", None)
            if callable(bind):
                bind(case_id, result.request_id or "")
            self.store.confirm_hosted_pending(
                case_id,
                result.operation_id,
                result.execution_id,
                result.request_id or "",
            )
            return
        if result.status == "automatic":
            apply_automatic = getattr(self.store, "apply_automatic", None)
            finish_automatic = getattr(self.store, "finish_automatic", None)
            if not callable(apply_automatic) or not callable(finish_automatic):
                raise CheckpointError("The application does not support automatic hosted outcomes.")
            apply_automatic(case_id, self.action)
            finish_automatic(case_id, result.execution_id)
            return
        if case.decision != result.status:
            raise CheckpointError("The hosted outcome conflicts with the recorded decision.")
        self.store.apply_once(case_id, result.status == "approved", self.action)
        self.store.finish(case_id, result.execution_id)

    async def _reconcile(self, case_id: UUID) -> None:
        case = self.store.get(case_id)
        start_operation = self._start_operation(case_id)
        start_unknown = case.status == "pending" and case.request_id == start_operation
        operation_id = (
            start_operation
            if start_unknown
            else self._resume_operation(case_id, case.decision or "")
        )
        result = await self.client.status(operation_id)
        if result.operation_id != operation_id:
            raise CheckpointError("The hosted status does not match the claimed operation.")
        if not start_unknown and result.status != case.decision:
            raise CheckpointError("The hosted resume status conflicts with the decision.")
        self._finish(case_id, result)

    @instrumented("workflow.start")
    async def start(self, case_id: UUID) -> None:
        with self.store.run_lock(case_id):
            case = self.store.get(case_id)
            if case.status == "pending" and case.failure_code == "hosted_outcome_unknown":
                await self._reconcile(case_id)
                return
            if case.status != "created":
                return
            operation_id = self._start_operation(case_id)
            self.store.claim_hosted_start(case_id, operation_id)
            try:
                result = await self.client.start(
                    HostedStart(
                        operation_id,
                        str(case.id),
                        case.tenant_id,
                        case.owner_id,
                        case.reviewer_id,
                        case.payload,
                    )
                )
            except HostedWorkflowError:
                raise
            if result.operation_id != operation_id:
                raise CheckpointError("The hosted start does not match the claimed operation.")
            self._finish(case_id, result)

    @instrumented("workflow.resume")
    async def resume(self, case_id: UUID) -> None:
        with self.store.run_lock(case_id):
            case = self.store.get(case_id)
            if case.execution_complete:
                return
            if case.failure_code == "hosted_outcome_unknown":
                await self._reconcile(case_id)
                return
            if case.decision is None:
                return
            if not case.checkpoint_id or not case.request_id:
                raise CheckpointError("The hosted workflow correlation is missing.")
            operation_id = self._resume_operation(case_id, case.decision)
            self.store.claim_hosted_resume(case_id)
            result = await self.client.resume(
                HostedResume(
                    operation_id,
                    str(case_id),
                    case.checkpoint_id,
                    case.request_id,
                    case.decision,
                    self.store.decision_actor(case_id),
                )
            )
            if result.operation_id != operation_id:
                raise CheckpointError("The hosted resume does not match the claimed operation.")
            if result.status != case.decision:
                raise CheckpointError("The hosted resume status conflicts with the decision.")
            self._finish(case_id, result)
