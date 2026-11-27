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
    """Opaque platform identity supplied by AgentServer protocol 2.0.0.

    The user ID identifies the authenticated API workload, not the human actor.
    Human authority is resolved from the pre-established conversation binding.
    """

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
    """Resolve human authority from an application-prebound conversation."""

    def resolve_start_principal(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
    ) -> Any:
        """Verify a pre-established owner binding and return its principal."""
        ...

    def authorize_resume(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
        channel: str,
    ) -> Any:
        """Verify a pre-established reviewer binding and return its principal."""
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
    ) -> dict[str, Any]: ...

    def authorize_resume(
        self,
        caller: CallerContext,
        conversation_id: str,
        request_id: str,
        value: Any,
    ) -> Any: ...

    def prewarm(self) -> None: ...


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
    def __init__(
        self,
        store: HostedBusinessStore,
        caller: CallerContext,
        conversation_id: str,
    ) -> None:
        self._store = store
        self._caller = caller
        self._conversation_id = conversation_id

    def _bound(self, principal_kind: str) -> HostedBusinessStore:
        return _bound_store(
            self._store,
            self._caller,
            self._conversation_id,
            principal_kind,
        )

    def get(self, case_id: UUID) -> Any:
        return self._bound("owner").get(case_id)

    def apply_automatic(self, case_id: UUID, action: Any) -> None:
        from app.order_resolution.observability import workflow_business_stage

        store = self._bound("owner")
        store.apply_automatic(case_id, action)
        with workflow_business_stage(
            "persistence",
            case_id=case_id,
            conversation_id=self._conversation_id,
            outcome="automatic",
        ):
            store.finish_hosted(case_id)

    def apply_once(self, case_id: UUID, approved: bool, action: Any) -> None:
        from app.order_resolution.observability import workflow_business_stage

        store = self._bound("reviewer")
        store.apply_once(case_id, approved, action)
        with workflow_business_stage(
            "persistence",
            case_id=case_id,
            conversation_id=self._conversation_id,
            outcome="approved" if approved else "rejected",
        ):
            store.finish_hosted(case_id)


def _bound_store(
    store: HostedBusinessStore,
    caller: CallerContext,
    conversation_id: str,
    principal_kind: str,
) -> HostedBusinessStore:
    factory = getattr(store, "for_binding", None)
    if callable(factory):
        return factory(caller, conversation_id, principal_kind)
    return store


def _require_application_principal(value: Any) -> Any:
    from app.domain.models import Principal

    if not isinstance(value, Principal):
        raise TypeError("The hosted identity resolver must return an application Principal.")
    return value


def _validate_hosted_decision(record: Any, command: Any, principal: Any) -> None:
    decision = getattr(command.decision, "value", command.decision)
    observed_decision = getattr(
        getattr(record, "decision", None),
        "value",
        getattr(record, "decision", None),
    )
    expected = (
        command.case_id,
        command.proposal_version,
        command.action,
        command.destination_id,
        decision,
        principal.subject,
        principal.tenant_id,
        command.scope,
        command.channel,
    )
    observed = (
        getattr(record, "case_id", None),
        getattr(record, "proposal_version", None),
        getattr(record, "action", None),
        getattr(record, "destination_id", None),
        observed_decision,
        getattr(record, "actor_id", None),
        getattr(record, "tenant_id", None),
        getattr(record, "scope", None),
        getattr(record, "channel", None),
    )
    if observed != expected:
        raise RuntimeError("The hosted decision acknowledgment is not authoritative.")


class GeneratedOrderResolutionApplication:
    """Bind the native workflow to authorization and the protected business API."""

    def __init__(
        self,
        *,
        store: HostedBusinessStore,
        action: Any,
        policy: Any,
        identity_bindings: HostedIdentityBindings,
        workflow_factory: Any,
        protected_self_decision_enabled: bool = False,
    ) -> None:
        self._store = store
        self._action = action
        self._policy = policy
        self._identity_bindings = identity_bindings
        self._workflow_factory = workflow_factory
        self._protected_self_decision_enabled = protected_self_decision_enabled

    @property
    def checkpoint_types(self) -> tuple[str, ...]:
        return ("app.order_resolution.workflow:OrderResolutionDecision",)

    def prewarm(self) -> None:
        prewarm = getattr(self._store, "prewarm", None)
        if callable(prewarm):
            prewarm()

    def build_workflow(self, caller: CallerContext, conversation_id: str) -> Any:
        if not conversation_id:
            raise PermissionError("A Foundry conversation binding is required.")
        return self._workflow_factory(
            _HostedWorkflowStore(self._store, caller, conversation_id),
            self._action,
            None,
        )

    def authorize_start(
        self,
        caller: CallerContext,
        conversation_id: str,
        case_id: UUID,
    ) -> dict[str, Any]:
        from app.order_resolution.observability import (
            capture_trace_link,
            workflow_business_stage,
        )

        with workflow_business_stage(
            "authorization",
            case_id=case_id,
            conversation_id=conversation_id,
        ):
            principal = _require_application_principal(
                self._identity_bindings.resolve_start_principal(
                    case_id=case_id,
                    caller=caller,
                    conversation_id=conversation_id,
                )
            )
            store = _bound_store(self._store, caller, conversation_id, "owner")
            case = store.get(case_id)
            self._policy.authorize_read(principal, case)
        with workflow_business_stage(
            "policy",
            case_id=case_id,
            conversation_id=conversation_id,
        ):
            proposal_payload = case.payload.get("proposal")
            if not isinstance(proposal_payload, dict):
                raise ValueError("The case does not contain an authoritative proposal.")
            approval_required = proposal_payload.get("approval_required")
            if not isinstance(approval_required, bool):
                raise ValueError("The proposal approval requirement is invalid.")
            allowed_statuses = ("created", "pending") if approval_required else ("created",)
            if case.status not in allowed_statuses:
                raise ValueError("The case is not eligible for a new hosted workflow run.")
        workflow_input: dict[str, Any] = {
            "case_id": str(case_id),
            "conversation_id": conversation_id,
        }
        trace_link = capture_trace_link()
        if trace_link is not None:
            workflow_input["trace_link"] = trace_link
        with workflow_business_stage(
            "proposal",
            case_id=case_id,
            conversation_id=conversation_id,
            approval_required=approval_required,
        ):
            if approval_required:
                request_id = _approval_request_id(case_id, caller, conversation_id)
                proposal = store.prepare_hosted_approval(
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
        from app.order_resolution.durability import (
            Actor,
            Decision,
            DecisionCommand,
            record_decision,
        )
        from app.order_resolution.workflow import OrderResolutionDecision
        from app.order_resolution.observability import workflow_business_stage

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
        if response.conversation_id != conversation_id or (
            response.session_id is not None and response.session_id != caller.session_id
        ):
            raise PermissionError("The workflow resume binding does not match this conversation.")

        with workflow_business_stage(
            "authorization",
            case_id=response.case_id,
            conversation_id=conversation_id,
            outcome=response.decision,
        ):
            principal = _require_application_principal(
                self._identity_bindings.authorize_resume(
                    case_id=response.case_id,
                    caller=caller,
                    conversation_id=conversation_id,
                    channel=response.channel,
                )
            )
            store = _bound_store(self._store, caller, conversation_id, "reviewer")
            case = store.get(response.case_id)
            from .business import _BoundBusinessStore

            # Only the authenticated API callback can decide a protected self-review.
            if not (
                self._protected_self_decision_enabled
                and type(store) is _BoundBusinessStore
                and case.owner_id == case.reviewer_id == principal.subject
                and case.tenant_id == principal.tenant_id
            ):
                self._policy.authorize_decision(principal, case)
        command = DecisionCommand(
            case_id=str(response.case_id),
            proposal_version=response.proposal_version,
            action=response.action,
            destination_id=response.destination_id,
            handle=response.handle,
            decision=Decision(response.decision),
            scope="workflow.approve",
            channel=response.channel,
        )
        with workflow_business_stage(
            "approval",
            case_id=response.case_id,
            conversation_id=conversation_id,
            outcome=response.decision,
            proposal_version=response.proposal_version,
        ):
            record_hosted_decision = getattr(store, "record_hosted_decision", None)
            if callable(record_hosted_decision):
                decision = record_hosted_decision(command)
                _validate_hosted_decision(decision, command, principal)
            else:
                record_decision(
                    _HostedDecisionStore(store),
                    store.get_current_proposal(str(response.case_id)),
                    Actor(
                        principal.tenant_id, principal.subject, principal.scopes, principal.roles
                    ),
                    command,
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
    from app.order_resolution.workflow import build_order_resolution_workflow

    from .business import HttpHostedBusinessStore

    store = HttpHostedBusinessStore.from_environment()
    return GeneratedOrderResolutionApplication(
        store=store,
        action=object(),
        policy=CaseAccessPolicy(),
        identity_bindings=store,
        workflow_factory=build_order_resolution_workflow,
        protected_self_decision_enabled=(
            os.environ.get("ORDER_RESOLUTION_POC_SELF_DECISION") == "true"
        ),
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
