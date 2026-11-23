import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.domain.errors import AccessDenied, Conflict, InvalidInput
from app.domain.models import AccessPolicy, BusinessRules, Case, Principal, WorkflowHost
from app.order_resolution.durability import (
    Actor,
    AuthorizationDenied,
    Conflict as DurabilityConflict,
    Decision as DurableDecision,
    DecisionCommand,
    record_decision,
)
from app.order_resolution.persistence import OrderResolutionStore
from app.usecases.service import WorkflowService


class OrderResolutionService(WorkflowService):
    """Bind decisions and effects to the current durable proposal."""

    store: OrderResolutionStore

    def __init__(
        self,
        store: OrderResolutionStore,
        host: WorkflowHost,
        rules: BusinessRules,
        policy: AccessPolicy,
        *,
        hosted_mode: bool = False,
    ) -> None:
        super().__init__(store, host, rules, policy)
        self.hosted_mode = hosted_mode

    async def submit(
        self,
        actor: Principal,
        reviewer_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> Case:
        self.policy.authorize_submission(actor, reviewer_id)
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
            raise InvalidInput("The idempotency key must be 1-128 safe characters.")
        validated = self.rules.validate(payload)
        canonical = json.dumps(
            {"reviewer_id": reviewer_id, "payload": validated},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        case = self.store.create(
            actor,
            reviewer_id,
            validated,
            idempotency_key,
            hashlib.sha256(canonical).hexdigest(),
        )
        failure = validated.get("resolution_failure")
        if isinstance(failure, str):
            if case.status == "created":
                self.store.fail_resolution(case.id, failure)
            return self.store.get(case.id)
        self.store.persist_proposal(case.id)
        try:
            await self.host.start(case.id, actor)
        except Conflict:
            pass
        return self.store.get(case.id)

    def record_bound_decision(
        self,
        actor: Principal,
        case_id: UUID,
        decision: str,
        *,
        proposal_version: int,
        action: str,
        destination_id: str,
        handle: str,
        channel: str,
        now: datetime | None = None,
        hosted_callback: bool = False,
    ):
        case = self.store.get(case_id)
        try:
            idempotent_repeat = case.decision == decision and case.status in (
                "approved",
                "rejected",
                "completed",
            )
            if not idempotent_repeat:
                self.policy.authorize_decision(actor, case)
            proposal = self.store.get_current_proposal(str(case_id))
            decision_store = self.store
            if hosted_callback:
                store = self.store

                class HostedDecisionStore:
                    get_current_proposal = store.get_current_proposal
                    claim_decision = store.claim_hosted_decision

                decision_store = HostedDecisionStore()
            return record_decision(
                decision_store,
                proposal,
                Actor(actor.tenant_id, actor.subject, actor.scopes, actor.roles),
                DecisionCommand(
                    case_id=str(case_id),
                    proposal_version=proposal_version,
                    action=action,
                    destination_id=destination_id,
                    handle=handle,
                    decision=DurableDecision(decision),
                    scope="workflow.approve",
                    channel=channel,
                ),
                now=now or datetime.now(timezone.utc),
            )
        except (AccessDenied, AuthorizationDenied) as exc:
            self.store.audit_authorization_denial(case_id, actor.subject)
            raise AccessDenied("Decision is not authorized.") from exc
        except DurabilityConflict as exc:
            raise Conflict(str(exc)) from exc
        except ValueError as exc:
            raise InvalidInput("The decision is invalid.") from exc

    async def decide_bound(
        self,
        actor: Principal,
        case_id: UUID,
        decision: str,
        *,
        proposal_version: int | None,
        action: str | None,
        destination_id: str | None,
        handle: str | None,
        channel: str | None,
    ) -> Case:
        if (
            proposal_version is None
            or action is None
            or destination_id is None
            or handle is None
            or channel is None
        ):
            self.store.audit_authorization_denial(case_id, actor.subject)
            raise AccessDenied("Decision is not authorized.")
        decision_command = DecisionCommand(
            case_id=str(case_id),
            proposal_version=proposal_version,
            action=action,
            destination_id=destination_id,
            handle=handle,
            decision=DurableDecision(decision),
            scope="workflow.approve",
            channel=channel,
        )
        if self.hosted_mode:
            try:
                await self.host.resume(case_id, actor, decision_command)
            except (AccessDenied, PermissionError) as exc:
                self.store.audit_authorization_denial(case_id, actor.subject)
                raise AccessDenied("Decision is not authorized.") from exc
        else:
            self.record_bound_decision(
                actor,
                case_id,
                decision,
                proposal_version=proposal_version,
                action=action,
                destination_id=destination_id,
                handle=handle,
                channel=channel,
            )
            await self.host.resume(case_id, actor, decision_command)
        return self.store.get(case_id)
