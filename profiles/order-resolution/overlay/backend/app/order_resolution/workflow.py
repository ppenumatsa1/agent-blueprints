from typing import Any, Literal, Protocol
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
from app.order_resolution.observability import (
    workflow_business_stage,
    workflow_marker_span,
    workflow_stage_span,
)
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
    async def resolve(self, message: dict[str, Any], ctx: WorkflowContext) -> None:
        case_id = UUID(message["case_id"])
        conversation_id = message.get("conversation_id")
        if not isinstance(conversation_id, str):
            conversation_id = f"local:{case_id}"
        with workflow_stage_span(
            "start",
            case_id=case_id,
            conversation_id=conversation_id,
        ):
            case = self._store.get(case_id)
            approval_required = case.payload["proposal"]["approval_required"]
            with workflow_business_stage(
                "approval",
                case_id=case_id,
                conversation_id=conversation_id,
                outcome="pending" if approval_required else "automatic",
                approval_required=approval_required,
            ):
                if approval_required:
                    request_id = message.get("request_id")
                    if request_id is not None and (
                        not request_id.strip() or len(request_id) > 256
                    ):
                        raise ValueError("The hosted request identity is invalid.")
                    request_data = {
                        "case_id": str(case_id),
                        "conversation_id": conversation_id,
                    }
                    trace_link = message.get("trace_link")
                    if isinstance(trace_link, dict):
                        request_data["trace_link"] = trace_link
                    with workflow_marker_span(
                        "hitl_waiting",
                        case_id=case_id,
                        conversation_id=conversation_id,
                        outcome="pending",
                    ):
                        await ctx.request_info(
                            request_data=request_data,
                            response_type=OrderResolutionDecision,
                            request_id=request_id,
                        )
                    return
            with workflow_business_stage(
                "effect",
                case_id=case_id,
                conversation_id=conversation_id,
                outcome="automatic",
            ):
                self._store.apply_automatic(case_id, self._action)
            await ctx.yield_output({"case_id": str(case_id), "decision": "automatic"})

    @response_handler
    async def handle_decision(
        self,
        original_request: dict[str, Any],
        response: OrderResolutionDecision,
        ctx: WorkflowContext,
    ) -> None:
        case_id = UUID(original_request["case_id"])
        if response.case_id != case_id:
            raise ValueError("The workflow response belongs to a different case.")
        conversation_id = original_request.get("conversation_id") or response.conversation_id
        if not isinstance(conversation_id, str):
            raise ValueError("The workflow resume conversation is missing.")
        with workflow_stage_span(
            "resume",
            case_id=case_id,
            conversation_id=conversation_id,
            trace_link=original_request.get("trace_link"),
        ):
            with workflow_marker_span(
                "hitl_resume",
                case_id=case_id,
                conversation_id=conversation_id,
                outcome=response.decision,
            ):
                with workflow_business_stage(
                    "effect",
                    case_id=case_id,
                    conversation_id=conversation_id,
                    outcome=response.decision,
                    proposal_version=response.proposal_version,
                ):
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
