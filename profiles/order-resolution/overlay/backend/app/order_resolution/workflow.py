from typing import Protocol
from uuid import UUID

from agent_framework import (
    CheckpointStorage,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

from app.domain.models import StateRepository, TransactionalAction
from app.workflows.workflow import WORKFLOW_NAME


class AutomaticResolutionStore(Protocol):
    def get(self, case_id: UUID): ...

    def apply_automatic(self, case_id: UUID, action: TransactionalAction) -> None: ...

    def apply_once(self, case_id: UUID, approved: bool, action: TransactionalAction) -> None: ...


class OrderResolutionExecutor(Executor):
    def __init__(self, store: AutomaticResolutionStore, action: TransactionalAction):
        super().__init__(id="approval")
        self._store = store
        self._action = action

    @handler
    async def resolve(self, message: dict[str, str], ctx: WorkflowContext) -> None:
        case_id = UUID(message["case_id"])
        case = self._store.get(case_id)
        if case.payload["proposal"]["approval_required"]:
            await ctx.request_info(request_data=message, response_type=bool)
            return
        self._store.apply_automatic(case_id, self._action)
        await ctx.yield_output({"case_id": str(case_id), "decision": "automatic"})

    @response_handler
    async def handle_decision(
        self, original_request: dict[str, str], approved: bool, ctx: WorkflowContext
    ) -> None:
        case_id = UUID(original_request["case_id"])
        self._store.apply_once(case_id, approved, self._action)
        await ctx.yield_output(
            {"case_id": str(case_id), "decision": "approved" if approved else "rejected"}
        )


def build_order_resolution_workflow(
    store: StateRepository,
    action: TransactionalAction,
    checkpoint_storage: CheckpointStorage | None = None,
) -> Workflow:
    """Compose the application with MAF's native workflow and host-owned checkpoints."""
    return WorkflowBuilder(
        name=WORKFLOW_NAME,
        start_executor=OrderResolutionExecutor(store, action),
        checkpoint_storage=checkpoint_storage,
    ).build()
