from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.api.dependencies import current_identity, workflow_service
from app.api.schemas import (
    ActivityOutput,
    CaseHistoryOutput,
    CaseOutput,
    DecisionInput,
    Submission,
    case_output,
)
from app.infrastructure.identity import AuthenticatedRequest
from app.order_resolution.service import OrderResolutionService
from app.usecases.service import WorkflowService

router = APIRouter(tags=["cases"])


@router.get("/cases", response_model=CaseHistoryOutput)
def history(
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
    status: Annotated[
        str | None,
        Query(pattern="^(created|pending|approved|rejected|completed|failed)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> CaseHistoryOutput:
    page = service.history(
        actor.principal,
        status=status,
        cursor=cursor,
        limit=limit,
    )
    return CaseHistoryOutput(
        items=[
            {
                "id": item.id,
                "status": item.status,
                "decision": item.decision or "pending",
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.post("/cases", response_model=CaseOutput)
async def submit(
    body: Submission,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
) -> CaseOutput:
    case = await service.submit(
        actor.principal, str(body.reviewer_id), body.payload, idempotency_key
    )
    return case_output(case)


@router.get("/cases/{case_id}/activity", response_model=ActivityOutput)
def activity(
    case_id: UUID,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ActivityOutput:
    page = service.activity(actor.principal, case_id, cursor=cursor, limit=limit)
    return ActivityOutput(
        items=[
            {"type": item.event_type, "created_at": item.created_at}
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/cases/{case_id}", response_model=CaseOutput)
def read(
    case_id: UUID,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> CaseOutput:
    return case_output(service.read(actor.principal, case_id))


@router.post("/cases/{case_id}/decision", response_model=CaseOutput)
async def decide(
    case_id: UUID,
    body: DecisionInput,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> CaseOutput:
    if isinstance(service, OrderResolutionService):
        case = await service.decide_bound(
            actor.principal,
            case_id,
            body.decision,
            proposal_version=body.proposal_version,
            action=body.action,
            destination_id=body.destination_id,
            handle=body.handle,
            channel=body.channel,
        )
    else:
        case = await service.decide(actor.principal, case_id, body.decision)
    return case_output(case)
