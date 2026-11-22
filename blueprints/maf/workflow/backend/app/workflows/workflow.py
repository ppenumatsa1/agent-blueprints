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


WORKFLOW_NAME = "approval-workflow-v1"


class ApprovalExecutor(Executor):
    def __init__(self, store: StateRepository, action: TransactionalAction):
        super().__init__(id="approval")
        self._store = store
        self._action = action

    @handler
    async def request_approval(self, message: dict[str, str], ctx: WorkflowContext) -> None:
        await ctx.request_info(request_data=message, response_type=bool)

    @response_handler
    async def handle_approval(
        self, original_request: dict[str, str], approved: bool, ctx: WorkflowContext
    ) -> None:
        case_id = UUID(original_request["case_id"])
        self._store.apply_once(case_id, approved, self._action)
        await ctx.yield_output({"case_id": str(case_id), "decision": "approved" if approved else "rejected"})


def create_workflow(
    store: StateRepository,
    action: TransactionalAction,
    checkpoint_storage: CheckpointStorage | None = None,
) -> Workflow:
    """Construct a native workflow; a host chooses and owns its checkpoint provider."""
    return WorkflowBuilder(
        name=WORKFLOW_NAME,
        start_executor=ApprovalExecutor(store, action),
        checkpoint_storage=checkpoint_storage,
    ).build()
