from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.models import Case


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: UUID
    payload: dict[str, Any]


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]


class CaseOutput(BaseModel):
    id: UUID
    correlation_id: UUID
    status: str
    decision: Literal["pending", "approved", "rejected"]
    payload: dict[str, Any]
    execution_complete: bool
    failure_code: str | None


def case_output(case: Case) -> CaseOutput:
    return CaseOutput(
        id=case.id,
        correlation_id=case.id,
        status=case.status,
        decision=case.decision or "pending",
        payload=case.payload,
        execution_complete=case.execution_complete,
        failure_code=case.failure_code,
    )
