from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.api.dependencies import current_identity, workflow_service
from app.api.schemas import CaseOutput, DecisionInput, Submission, case_output
from app.infrastructure.identity import AuthenticatedRequest
from app.usecases.service import WorkflowService

router = APIRouter(tags=["cases"])


@router.post("/cases", response_model=CaseOutput)
async def submit(
    body: Submission,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> CaseOutput:
    case = await service.submit(
        actor.principal, str(body.reviewer_id), body.payload, idempotency_key
    )
    return case_output(case)


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
    return case_output(await service.decide(actor.principal, case_id, body.decision))
