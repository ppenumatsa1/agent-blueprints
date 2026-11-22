from typing import Literal, Protocol
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
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import StateRepository, TransactionalAction
from app.workflows.workflow import WORKFLOW_NAME


class OrderResolutionDecision(BaseModel):
    """Structured native-workflow reply shared by local and hosted transports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: UUID
    proposal_version: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=256)
    destination_id: str = Field(min_length=1, max_length=256)
    handle: str = Field(min_length=1, max_length=256)
    channel: str = Field(min_length=1, max_length=64)
    decision: Literal["approved", "rejected"]
    conversation_id: str | None = Field(default=None, min_length=1, max_length=256)
    session_id: str | None = Field(default=None, min_length=1, max_length=256)

    @property
    def approved(self) -> bool:
        return self.decision == "approved"


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
            request_id = message.get("request_id")
            if request_id is not None and (not request_id.strip() or len(request_id) > 256):
                raise ValueError("The hosted request identity is invalid.")
            await ctx.request_info(
                request_data={"case_id": str(case_id)},
                response_type=OrderResolutionDecision,
                request_id=request_id,
            )
            return
        self._store.apply_automatic(case_id, self._action)
        await ctx.yield_output({"case_id": str(case_id), "decision": "automatic"})

    @response_handler
    async def handle_decision(
        self,
        original_request: dict[str, str],
        response: OrderResolutionDecision,
        ctx: WorkflowContext,
    ) -> None:
        case_id = UUID(original_request["case_id"])
        if response.case_id != case_id:
            raise ValueError("The workflow response belongs to a different case.")
        self._store.apply_once(case_id, response.approved, self._action)
        await ctx.yield_output(
            {
                "case_id": str(case_id),
                "decision": response.decision,
            }
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
