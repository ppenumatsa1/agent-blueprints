from datetime import datetime
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


CaseStatus = Literal["created", "pending", "approved", "rejected", "completed", "failed"]
ActivityType = Literal[
    "created",
    "review_requested",
    "request_recorded",
    "decision_recorded",
    "action_applied",
    "action_failed",
    "workflow_finished",
    "recovery_failed",
    "workflow_failed",
]


class CaseHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: CaseStatus
    decision: Literal["pending", "approved", "rejected"]
    created_at: datetime
    updated_at: datetime


class CaseHistoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workflow-history/1"] = "workflow-history/1"
    items: list[CaseHistoryItem]
    next_cursor: str | None


class ActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ActivityType
    created_at: datetime


class ActivityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workflow-activity/1"] = "workflow-activity/1"
    items: list[ActivityItem]
    next_cursor: str | None


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
