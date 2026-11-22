from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID

from azure.identity import DefaultAzureCredential

from .client import (
    FOUNDRY_SCOPE,
    ConversationBinding,
    OperationJournal,
    ResponsesClient,
    TokenProvider,
)


HOSTED_CHANNEL = "foundry-responses"


class HostedAuthorityBindings(Protocol):
    """Application-owned authority established before hosted dispatch."""

    def bind_start(
        self,
        case_id: UUID,
        principal: Any,
        *,
        caller_id: str,
        session_id: str,
        conversation_id: str,
        channel: str,
    ) -> None: ...

    def load_binding(self, case_id: UUID) -> ConversationBinding: ...

    def bind_resume(
        self,
        case_id: UUID,
        principal: Any,
        *,
        caller_id: str,
        session_id: str,
        conversation_id: str,
        channel: str,
        decision_command: Any,
    ) -> None: ...


def _actor_correlation(actor: Any) -> str:
    value = getattr(actor, "subject", None)
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise PermissionError("An authenticated application actor is required.")
    return value


def _decision_payload(
    case_id: UUID,
    command: Any,
    binding: ConversationBinding,
) -> dict[str, Any]:
    decision = getattr(getattr(command, "decision", None), "value", None)
    expected = (
        str(case_id),
        "workflow.approve",
        HOSTED_CHANNEL,
    )
    observed = (
        getattr(command, "case_id", None),
        getattr(command, "scope", None),
        getattr(command, "channel", None),
    )
    if observed != expected or decision not in ("approved", "rejected"):
        raise PermissionError("The hosted decision command is not authorized.")
    values = {
        "proposal_version": getattr(command, "proposal_version", None),
        "action": getattr(command, "action", None),
        "destination_id": getattr(command, "destination_id", None),
        "handle": getattr(command, "handle", None),
    }
    if (
        not isinstance(values["proposal_version"], int)
        or values["proposal_version"] < 1
        or any(
            not isinstance(values[name], str) or not values[name]
            for name in ("action", "destination_id", "handle")
        )
    ):
        raise PermissionError("The hosted decision command is incomplete.")
    return {
        "case_id": str(case_id),
        **values,
        "decision": decision,
        "conversation_id": binding.conversation_id,
        "session_id": binding.session_id,
        "channel": HOSTED_CHANNEL,
    }


class ResponsesWorkflowHost:
    """API-side bridge from authenticated commands to native Responses."""

    def __init__(
        self,
        responses: ResponsesClient,
        authority_bindings: HostedAuthorityBindings,
    ) -> None:
        self._responses = responses
        self._authority_bindings = authority_bindings

    async def start(self, case_id: UUID, actor: Any) -> None:
        caller_id = _actor_correlation(actor)
        session_id = f"case:{case_id}"
        binding = await asyncio.to_thread(
            self._responses.create_conversation,
            operation_id=f"case:{case_id}:conversation",
            caller_id=caller_id,
            session_id=session_id,
        )
        await asyncio.to_thread(
            self._authority_bindings.bind_start,
            case_id,
            actor,
            caller_id=binding.caller_id,
            session_id=binding.session_id,
            conversation_id=binding.conversation_id,
            channel=HOSTED_CHANNEL,
        )
        await asyncio.to_thread(
            self._responses.start,
            operation_id=f"case:{case_id}:start",
            binding=binding,
            case_id=str(case_id),
        )

    async def resume(self, case_id: UUID, actor: Any, decision_command: Any) -> None:
        caller_id = _actor_correlation(actor)
        existing = await asyncio.to_thread(self._authority_bindings.load_binding, case_id)
        if not isinstance(existing, ConversationBinding):
            raise TypeError("The hosted authority adapter returned an invalid binding.")
        binding = ConversationBinding(
            caller_id=caller_id,
            conversation_id=existing.conversation_id,
            session_id=existing.session_id,
        )
        payload = _decision_payload(case_id, decision_command, binding)
        await asyncio.to_thread(
            self._authority_bindings.bind_resume,
            case_id,
            actor,
            caller_id=binding.caller_id,
            session_id=binding.session_id,
            conversation_id=binding.conversation_id,
            channel=HOSTED_CHANNEL,
            decision_command=decision_command,
        )
        await asyncio.to_thread(
            self._responses.resume,
            operation_id=f"case:{case_id}:decision:{payload['proposal_version']}",
            binding=binding,
            request_id=payload["handle"],
            decision=payload,
        )


def build_workflow_host(
    settings: Any,
    store: Any,
    authority_bindings: HostedAuthorityBindings,
    operation_journal: OperationJournal,
) -> ResponsesWorkflowHost:
    """Build the explicit generated API-to-Responses adapter."""

    if store is None:
        raise TypeError("The application-owned Order Resolution store is required.")
    scope = getattr(settings, "hosted_workflow_scope", None)
    client_id = getattr(settings, "api_managed_identity_client_id", None)
    if scope != FOUNDRY_SCOPE:
        raise ValueError(f"The hosted workflow scope must be {FOUNDRY_SCOPE}.")
    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("The API managed identity client ID is required.")
    credential = DefaultAzureCredential(managed_identity_client_id=client_id)
    responses = ResponsesClient(
        getattr(settings, "hosted_workflow_endpoint", ""),
        operation_journal,
        conversation_endpoint=getattr(settings, "hosted_conversation_endpoint", ""),
        token_provider=TokenProvider(credential),
    )
    return ResponsesWorkflowHost(responses, authority_bindings)
