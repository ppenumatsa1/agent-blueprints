from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import current_identity, workflow_service
from app.domain.errors import AccessDenied, NotFound
from app.infrastructure.identity import AuthenticatedRequest
from app.order_resolution.acceptance import AcceptanceFaults
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.service import OrderResolutionService
from app.usecases.service import WorkflowService

router = APIRouter(prefix="/acceptance", tags=["acceptance"])


class ControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_revision: str
    enabled: bool


def _authorized(
    actor: AuthenticatedRequest,
    workflow: WorkflowService,
    deployment_revision: str,
) -> tuple[OrderResolutionStore, AcceptanceFaults]:
    if "Acceptance.Operator" not in actor.principal.roles:
        raise AccessDenied("Acceptance control is not authorized.")
    if not isinstance(workflow, OrderResolutionService) or not isinstance(
        workflow.store, OrderResolutionStore
    ):
        raise NotFound("Acceptance controls are unavailable.")
    faults = getattr(workflow.store, "acceptance_faults", None)
    if not isinstance(faults, AcceptanceFaults):
        raise NotFound("Acceptance controls are unavailable.")
    try:
        faults.authorize_revision(deployment_revision)
    except PermissionError as exc:
        raise AccessDenied("Acceptance control is not authorized.") from exc
    return workflow.store, faults


@router.post("/faults/postgres-transient")
def postgres_transient(
    body: ControlInput,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    workflow: Annotated[WorkflowService, Depends(workflow_service)],
) -> dict[str, object]:
    _, faults = _authorized(actor, workflow, body.deployment_revision)
    faults.set_postgres_transient(body.enabled)
    return {"fault": "postgres-transient", "enabled": body.enabled}


@router.post("/cases/{case_id}/faults/{fault}")
def case_fault(
    case_id: UUID,
    fault: Literal["decision-ack-lost", "effect-ack-lost"],
    body: ControlInput,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    workflow: Annotated[WorkflowService, Depends(workflow_service)],
) -> dict[str, object]:
    _, faults = _authorized(actor, workflow, body.deployment_revision)
    faults.set_ack_fault(case_id, fault, body.enabled)
    return {"case_id": str(case_id), "fault": fault, "enabled": body.enabled}


@router.get("/cases/{case_id}")
def case_control(
    case_id: UUID,
    deployment_revision: str,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    workflow: Annotated[WorkflowService, Depends(workflow_service)],
) -> dict[str, object]:
    store, faults = _authorized(actor, workflow, deployment_revision)
    binding = store.acceptance_binding(case_id)
    return {
        "case_id": str(case_id),
        "conversation_id": binding["conversation_id"],
        "platform_session_id": binding["session_id"],
        "armed_faults": faults.armed(case_id),
        "observed_faults": faults.observed(case_id),
        "snapshot": store.acceptance_snapshot(case_id),
    }
