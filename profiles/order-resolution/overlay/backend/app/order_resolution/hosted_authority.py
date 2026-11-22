from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain.errors import AccessDenied
from app.domain.models import Principal
from app.order_resolution.durability import DecisionCommand
from app.order_resolution.persistence import (
    HOSTED_CHANNEL,
    HostedConversationBinding,
    OrderResolutionStore,
)


class PostgresHostedAuthorityBindings:
    """Persist only authority established by an authenticated human API command."""

    def __init__(self, store: OrderResolutionStore) -> None:
        self._store = store

    def bind_start(
        self,
        case_id: UUID,
        principal: Principal,
        *,
        conversation_id: str,
        channel: str,
    ) -> None:
        self._bind(
            case_id,
            principal,
            conversation_id=conversation_id,
            channel=channel,
        )

    def bind_resume(
        self,
        case_id: UUID,
        principal: Principal,
        *,
        conversation_id: str,
        channel: str,
        decision_command: DecisionCommand,
    ) -> None:
        if channel != HOSTED_CHANNEL:
            raise AccessDenied("The hosted channel is not authorized.")
        self._store.bind_hosted_resume_authority(
            case_id,
            principal,
            conversation_id=conversation_id,
            channel=channel,
            decision_command=decision_command,
        )

    def load_binding(self, case_id: UUID) -> Any:
        binding: HostedConversationBinding = self._store.load_hosted_binding(case_id)
        from order_resolution_hosted.client import ConversationBinding

        return ConversationBinding(conversation_id=binding.conversation_id)

    def _bind(
        self,
        case_id: UUID,
        principal: Principal,
        *,
        conversation_id: str,
        channel: str,
    ) -> None:
        if channel != HOSTED_CHANNEL:
            raise AccessDenied("The hosted channel is not authorized.")
        self._store.bind_hosted_principal(
            case_id,
            principal,
            conversation_id=conversation_id,
            principal_kind="owner",
        )
