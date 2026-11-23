import hashlib
import json
from datetime import datetime
from typing import Annotated, Callable, Literal, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import current_service_identity, workflow_service
from app.domain.errors import HostedWorkflowError, InvalidInput
from app.domain.models import Principal
from app.infrastructure.identity import AuthenticatedRequest
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.durability import DecisionRecord, Proposal
from app.order_resolution.persistence import (
    HOSTED_CHANNEL,
    OrderResolutionStore,
)
from app.order_resolution.service import OrderResolutionService
from app.usecases.service import WorkflowService

router = APIRouter(tags=["hosted-service"])
ResultT = TypeVar("ResultT")


class BindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_user_id: str = Field(min_length=1, max_length=512)
    platform_session_id: str = Field(min_length=1, max_length=512)
    platform_call_id: str = Field(min_length=1, max_length=512)
    conversation_id: str = Field(min_length=1, max_length=512)
    channel: Literal["foundry-responses"] = HOSTED_CHANNEL


class BoundReadInput(BindingInput):
    principal_kind: Literal["owner", "reviewer"]


class PrepareApprovalInput(BindingInput):
    request_id: str = Field(min_length=1, max_length=512)


class ClaimDecisionInput(BindingInput):
    proposal_version: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=256)
    destination_id: str = Field(min_length=1, max_length=256)
    handle: str = Field(min_length=1, max_length=512)
    decision: Literal["approved", "rejected"]


class ApplyEffectInput(BindingInput):
    mode: Literal["automatic", "approved", "rejected"]


class FinishHostedInput(BindingInput):
    mode: Literal["automatic", "approved", "rejected"]


class PrincipalOutput(BaseModel):
    tenant_id: str
    subject: str
    scopes: list[str]
    roles: list[str]


class HostedCaseOutput(BaseModel):
    id: UUID
    tenant_id: str
    owner_id: str
    reviewer_id: str
    payload: dict
    status: str
    decision: Literal["approved", "rejected"] | None
    request_id: str | None
    execution_complete: bool
    failure_code: str | None


class ProposalOutput(BaseModel):
    case_id: str
    proposal_version: int
    tenant_id: str
    owner_id: str
    reviewer_id: str
    input_digest: str
    policy_evidence_digest: str
    policy_version: str
    action: str
    destination_id: str
    approval_required: bool
    reason_codes: list[str]
    decision_handle_digest: str | None
    decision_expires_at: datetime | None
    decision_channel: str | None


class DecisionOutput(BaseModel):
    case_id: str
    proposal_version: int
    action: str
    destination_id: str
    decision: Literal["approved", "rejected"]
    actor_id: str
    tenant_id: str
    scope: str
    channel: str
    decided_at: datetime


def _service(value: WorkflowService) -> OrderResolutionService:
    if not isinstance(value, OrderResolutionService):
        raise HostedWorkflowError("The Order Resolution hosted service is unavailable.")
    return value


def _store(value: WorkflowService) -> OrderResolutionStore:
    service = _service(value)
    if not isinstance(service.store, OrderResolutionStore):
        raise HostedWorkflowError("The Order Resolution store is unavailable.")
    return service.store


def _principal(principal) -> PrincipalOutput:
    return PrincipalOutput(
        tenant_id=principal.tenant_id,
        subject=principal.subject,
        scopes=sorted(principal.scopes),
        roles=sorted(principal.roles),
    )


def _case(case) -> HostedCaseOutput:
    return HostedCaseOutput(
        id=case.id,
        tenant_id=case.tenant_id,
        owner_id=case.owner_id,
        reviewer_id=case.reviewer_id,
        payload=case.payload,
        status=case.status,
        decision=case.decision,
        request_id=case.request_id,
        execution_complete=case.execution_complete,
        failure_code=case.failure_code,
    )


def _proposal(proposal: Proposal) -> ProposalOutput:
    return ProposalOutput(
        **{
            **proposal.__dict__,
            "reason_codes": list(proposal.reason_codes),
        }
    )


def _decision(decision: DecisionRecord) -> DecisionOutput:
    return DecisionOutput(
        **{
            **decision.__dict__,
            "decision": decision.decision.value,
        }
    )


def _idempotent(
    store: OrderResolutionStore,
    case_id: UUID,
    operation_id: str,
    operation_kind: Literal["start", "resume"],
    operation_label: str,
    body: BaseModel,
    operation: Callable[[], ResultT],
) -> ResultT:
    if (
        not operation_id
        or len(operation_id) > 256
        or not operation_id.startswith(f"case:{case_id}:")
    ):
        raise InvalidInput("The Idempotency-Key must be bounded and case-bound.")
    logical_body = body.model_dump(mode="json")
    logical_body.pop("platform_call_id", None)
    request_digest = hashlib.sha256(
        json.dumps(
            {
                "operation": operation_label,
                "body": logical_body,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    store.claim_hosted_operation(
        case_id,
        operation_id,
        operation_kind,
        request_digest,
    )
    result = operation()
    store.update_hosted_operation(
        operation_id,
        request_digest,
        "acknowledged",
        operation_id,
    )
    faults = getattr(store, "acceptance_faults", None)
    if faults is not None and faults.consume_ack_fault(case_id, operation_label):
        raise HostedWorkflowError("Synthetic acceptance acknowledgment loss.")
    return result


def _authorize_binding(
    store: OrderResolutionStore,
    case_id: UUID,
    body: BindingInput,
    principal_kind: Literal["owner", "reviewer"],
) -> Principal:
    return store.authorize_hosted_binding(
        case_id,
        conversation_id=body.conversation_id,
        channel=body.channel,
        principal_kind=principal_kind,
    )


def _apply_effect(
    store: OrderResolutionStore,
    case_id: UUID,
    mode: Literal["automatic", "approved", "rejected"],
) -> HostedCaseOutput:
    action = RecordOrderResolutionAction().bind(store)
    if mode == "automatic":
        store.apply_automatic(case_id, action)
    else:
        store.apply_once(case_id, mode == "approved", action)
    return _case(store.get(case_id))


def _finish_hosted(
    store: OrderResolutionStore,
    case_id: UUID,
) -> HostedCaseOutput:
    store.finish_hosted(case_id)
    return _case(store.get(case_id))


@router.post("/cases/{case_id}/bindings/start", response_model=PrincipalOutput)
def bind_start(
    case_id: UUID,
    body: BindingInput,
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> PrincipalOutput:
    store = _store(service)
    principal = store.resolve_hosted_start_principal(
        case_id,
        conversation_id=body.conversation_id,
        channel=body.channel,
    )
    store.record_hosted_platform_binding(
        case_id,
        conversation_id=body.conversation_id,
        caller_id=body.platform_user_id,
        session_id=body.platform_session_id,
    )
    return _principal(principal)


@router.post("/cases/{case_id}/bindings/resume", response_model=PrincipalOutput)
def bind_resume(
    case_id: UUID,
    body: BindingInput,
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> PrincipalOutput:
    store = _store(service)
    principal = store.authorize_hosted_resume(
        case_id,
        conversation_id=body.conversation_id,
        channel=body.channel,
    )
    store.record_hosted_platform_binding(
        case_id,
        conversation_id=body.conversation_id,
        caller_id=body.platform_user_id,
        session_id=body.platform_session_id,
    )
    return _principal(principal)


@router.post("/cases/{case_id}/read", response_model=HostedCaseOutput)
def read_case(
    case_id: UUID,
    body: BoundReadInput,
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> HostedCaseOutput:
    store = _store(service)
    _authorize_binding(store, case_id, body, body.principal_kind)
    return _case(store.get(case_id))


@router.post("/cases/{case_id}/proposal/read", response_model=ProposalOutput)
def read_proposal(
    case_id: UUID,
    body: BoundReadInput,
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> ProposalOutput:
    store = _store(service)
    _authorize_binding(store, case_id, body, body.principal_kind)
    return _proposal(store.get_current_proposal(str(case_id)))


@router.post("/cases/{case_id}/approvals/prepare", response_model=ProposalOutput)
def prepare_approval(
    case_id: UUID,
    body: PrepareApprovalInput,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> ProposalOutput:
    store = _store(service)
    _authorize_binding(store, case_id, body, "owner")
    return _idempotent(
        store,
        case_id,
        idempotency_key,
        "start",
        "prepare-approval",
        body,
        lambda: _proposal(
            store.prepare_hosted_approval(
                case_id,
                body.request_id,
                channel=body.channel,
            )
        ),
    )


@router.post("/cases/{case_id}/decisions/claim", response_model=DecisionOutput)
def claim_decision(
    case_id: UUID,
    body: ClaimDecisionInput,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    workflow: Annotated[WorkflowService, Depends(workflow_service)],
) -> DecisionOutput:
    service = _service(workflow)
    store = _store(service)
    actor = _authorize_binding(store, case_id, body, "reviewer")
    return _idempotent(
        store,
        case_id,
        idempotency_key,
        "resume",
        "claim-decision",
        body,
        lambda: _decision(
            service.record_bound_decision(
                actor,
                case_id,
                body.decision,
                proposal_version=body.proposal_version,
                action=body.action,
                destination_id=body.destination_id,
                handle=body.handle,
                channel=body.channel,
                hosted_callback=True,
            )
        ),
    )


@router.post("/cases/{case_id}/effects/apply", response_model=HostedCaseOutput)
def apply_effect(
    case_id: UUID,
    body: ApplyEffectInput,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> HostedCaseOutput:
    store = _store(service)
    principal_kind = "owner" if body.mode == "automatic" else "reviewer"
    _authorize_binding(store, case_id, body, principal_kind)
    return _idempotent(
        store,
        case_id,
        idempotency_key,
        "start" if body.mode == "automatic" else "resume",
        "apply-effect",
        body,
        lambda: _apply_effect(store, case_id, body.mode),
    )


@router.post("/cases/{case_id}/finish", response_model=HostedCaseOutput)
def finish_hosted(
    case_id: UUID,
    body: FinishHostedInput,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    _: Annotated[AuthenticatedRequest, Depends(current_service_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
) -> HostedCaseOutput:
    store = _store(service)
    principal_kind = "owner" if body.mode == "automatic" else "reviewer"
    _authorize_binding(store, case_id, body, principal_kind)
    return _idempotent(
        store,
        case_id,
        idempotency_key,
        "start" if body.mode == "automatic" else "resume",
        "finish-hosted",
        body,
        lambda: _finish_hosted(store, case_id),
    )
