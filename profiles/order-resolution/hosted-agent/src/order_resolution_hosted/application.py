from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID


FOUNDRY_RESPONSES_CHANNEL = "foundry-responses"


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


class GeneratedOrderResolutionApplication:
    """Bind the native workflow to application authorization and PostgreSQL state."""

    def __init__(
        self,
        *,
        store: Any,
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
        return self._workflow_factory(self._store, self._action, None)

    def authorize_start(
        self,
        caller: CallerContext,
        conversation_id: str,
        case_id: UUID,
    ) -> dict[str, str]:
        principal = self._identity_bindings.resolve_principal(caller)
        case = self._store.get(case_id)
        self._policy.authorize_read(principal, case)
        if case.status != "created":
            raise ValueError("The case is not eligible for a new hosted workflow run.")
        self._identity_bindings.bind_start(
            case_id=case_id,
            caller=caller,
            conversation_id=conversation_id,
        )
        return {"case_id": str(case_id)}

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
            raise PermissionError("The approval handle does not match the pending workflow request.")
        if response.channel != FOUNDRY_RESPONSES_CHANNEL:
            raise PermissionError("Cross-channel workflow resume is not authorized.")
        if (
            response.conversation_id != conversation_id
            or response.session_id != caller.session_id
        ):
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
        proposal = self._store.bind_decision_handle(
            response.case_id,
            request_id,
            channel=response.channel,
        )
        record_decision(
            self._store,
            proposal,
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
