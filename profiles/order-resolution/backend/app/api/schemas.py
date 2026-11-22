from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import Case


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: UUID
    payload: dict[str, Any]


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    proposal_version: int | None = Field(default=None, ge=1)
    action: str | None = Field(default=None, min_length=1, max_length=128)
    destination_id: str | None = Field(default=None, min_length=1, max_length=128)
    handle: str | None = Field(default=None, min_length=1, max_length=256)
    channel: str | None = Field(default=None, min_length=1, max_length=64)


class CaseOutput(BaseModel):
    id: UUID
    correlation_id: UUID
    status: str
    decision: Literal["pending", "approved", "rejected"]
    payload: dict[str, Any]
    decision_handle: str | None
    execution_complete: bool
    failure_code: str | None


def case_output(case: Case) -> CaseOutput:
    return CaseOutput(
        id=case.id,
        correlation_id=case.id,
        status=case.status,
        decision=case.decision or "pending",
        payload=case.payload,
        decision_handle=(
            case.request_id if case.status == "pending" and case.decision is None else None
        ),
        execution_complete=case.execution_complete,
        failure_code=case.failure_code,
    )
