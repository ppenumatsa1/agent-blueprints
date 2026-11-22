from __future__ import annotations

import importlib
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5


FOUNDRY_RESPONSES_CHANNEL = "foundry-responses"


def _approval_request_id(
    case_id: UUID,
    caller: "CallerContext",
    conversation_id: str,
) -> str:
    identity = json.dumps(
        [
            "order-resolution-hosted-approval-v1",
            str(case_id),
            caller.user_id,
            caller.session_id,
            conversation_id,
            FOUNDRY_RESPONSES_CHANNEL,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return str(uuid5(NAMESPACE_URL, identity))


@dataclass(frozen=True)
class CallerContext:
    """Trusted request identity supplied by AgentServer protocol 2.0.0."""

    user_id: str
    session_id: str
    call_id: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.user_id, "Foundry user"),
            (self.session_id, "Foundry session"),
            (self.call_id, "Foundry call"),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise PermissionError(f"{label} identity is required.")


class HostedIdentityBindings(Protocol):
    """Application-owned bridge from opaque Foundry identity to API authority."""

    def resolve_principal(self, caller: CallerContext) -> Any:
        """Resolve a current application principal without trusting client input."""
        ...

    def bind_start(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
    ) -> None:
        """Create or verify the authoritative case/caller/session/conversation binding."""
        ...

    def authorize_resume(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
        channel: str,
    ) -> None:
        """Reject a different caller, session, conversation, or channel."""
        ...


class HostedApplication(Protocol):
    @property
    def checkpoint_types(self) -> tuple[str, ...]: ...

    def build_workflow(self, caller: CallerContext, conversation_id: str) -> Any: ...

    def authorize_start(
        self,
        caller: CallerContext,
        conversation_id: str,
        case_id: UUID,
    ) -> dict[str, str]: ...

    def authorize_resume(
        self,
        caller: CallerContext,
        conversation_id: str,
        request_id: str,
        value: Any,
    ) -> Any: ...


class HostedBusinessStore(Protocol):
    """Application-owned business lifecycle correlated to hosted workflow state."""

    def get(self, case_id: UUID) -> Any: ...

    def prepare_hosted_approval(
        self,
        case_id: UUID,
        candidate_request_id: str,
        *,
        channel: str,
    ) -> Any: ...

    def get_current_proposal(self, case_id: str) -> Any: ...

    def claim_hosted_decision(self, decision: Any) -> Any: ...

    def apply_automatic(self, case_id: UUID, action: Any) -> None: ...

    def apply_once(self, case_id: UUID, approved: bool, action: Any) -> None: ...

    def finish_hosted(self, case_id: UUID) -> None: ...


class _HostedDecisionStore:
    def __init__(self, store: HostedBusinessStore) -> None:
        self._store = store

    def get_current_proposal(self, case_id: str) -> Any:
        return self._store.get_current_proposal(case_id)

    def claim_decision(self, decision: Any) -> Any:
        return self._store.claim_hosted_decision(decision)


class _HostedWorkflowStore:
    def __init__(self, store: HostedBusinessStore) -> None:
        self._store = store

    def get(self, case_id: UUID) -> Any:
        return self._store.get(case_id)

    def apply_automatic(self, case_id: UUID, action: Any) -> None:
        self._store.apply_automatic(case_id, action)
        self._store.finish_hosted(case_id)

    def apply_once(self, case_id: UUID, approved: bool, action: Any) -> None:
        self._store.apply_once(case_id, approved, action)
        self._store.finish_hosted(case_id)


class GeneratedOrderResolutionApplication:
    """Bind the native workflow to application authorization and PostgreSQL state."""

    def __init__(
        self,
        *,
        store: HostedBusinessStore,
        action: Any,
        policy: Any,
        identity_bindings: HostedIdentityBindings,
        workflow_factory: Any,
    ) -> None:
        self._store = store
        self._action = action
        self._policy = policy
        self._identity_bindings = identity_bindings
        self._workflow_factory = workflow_factory

    @property
    def checkpoint_types(self) -> tuple[str, ...]:
        return ("app.order_resolution.workflow:OrderResolutionDecision",)

    def build_workflow(self, caller: CallerContext, conversation_id: str) -> Any:
        self._identity_bindings.resolve_principal(caller)
        if not conversation_id:
            raise PermissionError("A Foundry conversation binding is required.")
        return self._workflow_factory(_HostedWorkflowStore(self._store), self._action, None)

    def authorize_start(
        self,
        caller: CallerContext,
        conversation_id: str,
        case_id: UUID,
    ) -> dict[str, str]:
        principal = self._identity_bindings.resolve_principal(caller)
        case = self._store.get(case_id)
        self._policy.authorize_read(principal, case)
        approval_required = case.payload["proposal"]["approval_required"]
        allowed_statuses = ("created", "pending") if approval_required else ("created",)
        if case.status not in allowed_statuses:
            raise ValueError("The case is not eligible for a new hosted workflow run.")
        self._identity_bindings.bind_start(
            case_id=case_id,
            caller=caller,
            conversation_id=conversation_id,
        )
        workflow_input = {"case_id": str(case_id)}
        if approval_required:
            request_id = _approval_request_id(case_id, caller, conversation_id)
            proposal = self._store.prepare_hosted_approval(
                case_id,
                request_id,
                channel=FOUNDRY_RESPONSES_CHANNEL,
            )
            expected_digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
            if (
                not hmac.compare_digest(
                    getattr(proposal, "decision_handle_digest", "") or "",
                    expected_digest,
                )
                or getattr(proposal, "decision_channel", None) != FOUNDRY_RESPONSES_CHANNEL
            ):
                raise RuntimeError(
                    "The hosted business store did not bind the native request identity."
                )
            workflow_input["request_id"] = request_id
        return workflow_input

    def authorize_resume(
        self,
        caller: CallerContext,
        conversation_id: str,
        request_id: str,
        value: Any,
    ) -> Any:
        from app.domain.models import Principal
        from app.order_resolution.durability import (
            Actor,
            Decision,
            DecisionCommand,
            record_decision,
        )
        from app.order_resolution.workflow import OrderResolutionDecision

        response = (
            value
            if isinstance(value, OrderResolutionDecision)
            else OrderResolutionDecision.model_validate(value)
        )
        if response.handle != request_id:
            raise PermissionError(
                "The approval handle does not match the pending workflow request."
            )
        if response.channel != FOUNDRY_RESPONSES_CHANNEL:
            raise PermissionError("Cross-channel workflow resume is not authorized.")
        if response.conversation_id != conversation_id or response.session_id != caller.session_id:
            raise PermissionError("The workflow resume binding does not match this conversation.")

        principal = self._identity_bindings.resolve_principal(caller)
        if not isinstance(principal, Principal):
            raise TypeError("The hosted identity resolver must return an application Principal.")
        case = self._store.get(response.case_id)
        self._policy.authorize_decision(principal, case)
        self._identity_bindings.authorize_resume(
            case_id=response.case_id,
            caller=caller,
            conversation_id=conversation_id,
            channel=response.channel,
        )
        record_decision(
            _HostedDecisionStore(self._store),
            self._store.get_current_proposal(str(response.case_id)),
            Actor(principal.tenant_id, principal.subject, principal.scopes, principal.roles),
            DecisionCommand(
                case_id=str(response.case_id),
                proposal_version=response.proposal_version,
                action=response.action,
                destination_id=response.destination_id,
                handle=response.handle,
                decision=Decision(response.decision),
                scope="workflow.approve",
                channel=response.channel,
            ),
            now=datetime.now(timezone.utc),
        )
        return response


def _load_factory(specification: str) -> Any:
    module_name, separator, factory_name = specification.partition(":")
    if not module_name or not separator or not factory_name:
        raise ValueError("A factory must use module:function syntax.")
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory()


def build_generated_application() -> GeneratedOrderResolutionApplication:
    """Compose the generated app without importing or attaching its local checkpoint host."""

    from app.domain.policy import CaseAccessPolicy
    from app.order_resolution.action import RecordOrderResolutionAction
    from app.order_resolution.migrations import validate_connection
    from app.order_resolution.persistence import OrderResolutionStore
    from app.order_resolution.workflow import build_order_resolution_workflow

    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise ValueError("DATABASE_URL is required.")
    bindings_spec = os.environ.get("ORDER_RESOLUTION_HOSTED_IDENTITY_BINDINGS", "").strip()
    if not bindings_spec:
        raise ValueError(
            "ORDER_RESOLUTION_HOSTED_IDENTITY_BINDINGS must name an authorized module:function."
        )
    identity_bindings = _load_factory(bindings_spec)
    store = OrderResolutionStore(dsn)
    with store.connect() as connection:
        validate_connection(connection)
    return GeneratedOrderResolutionApplication(
        store=store,
        action=RecordOrderResolutionAction().bind(store),
        policy=CaseAccessPolicy(),
        identity_bindings=identity_bindings,
        workflow_factory=build_order_resolution_workflow,
    )


def load_application() -> HostedApplication:
    specification = os.environ.get(
        "ORDER_RESOLUTION_HOSTED_APPLICATION",
        "order_resolution_hosted.application:build_generated_application",
    )
    application = _load_factory(specification)
    for member in (
        "build_workflow",
        "authorize_start",
        "authorize_resume",
        "checkpoint_types",
    ):
        if not hasattr(application, member):
            raise TypeError(f"The hosted application is missing {member}.")
    return application
