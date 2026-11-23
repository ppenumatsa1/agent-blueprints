import hashlib
import json
import re
from typing import Any
from uuid import UUID

from app.domain.errors import AccessDenied, InvalidInput
from app.domain.models import (
    AccessPolicy,
    BusinessRules,
    Case,
    Decision,
    Principal,
    StateRepository,
    WorkflowHost,
)
from app.usecases.history import (
    ActivityPage,
    HistoryPage,
    activity_page,
    decode_activity_cursor,
    decode_history_cursor,
    history_page,
)


class WorkflowService:
    def __init__(
        self,
        store: StateRepository,
        host: WorkflowHost,
        rules: BusinessRules,
        policy: AccessPolicy,
    ):
        self.store = store
        self.host = host
        self.rules = rules
        self.policy = policy

    async def submit(
        self, actor: Principal, reviewer_id: str, payload: dict[str, Any], idempotency_key: str
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
            actor, reviewer_id, validated, idempotency_key, hashlib.sha256(canonical).hexdigest()
        )
        await self.host.start(case.id, actor)
        return self.store.get(case.id)

    def read(self, actor: Principal, case_id: UUID) -> Case:
        case = self.store.get(case_id)
        self.policy.authorize_read(actor, case)
        return case

    def history(
        self,
        actor: Principal,
        *,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> HistoryPage:
        if "workflow.read" not in actor.scopes:
            raise AccessDenied("Record access is not authorized.")
        if not 1 <= limit <= 100:
            raise InvalidInput("The history page size is invalid.")
        if status is not None and status not in (
            "created",
            "pending",
            "approved",
            "rejected",
            "completed",
            "failed",
        ):
            raise InvalidInput("The history status is invalid.")
        position = decode_history_cursor(cursor, status)
        items, has_more = self.store.list_history(actor, status, position, limit)
        return history_page(items, has_more, status)

    def activity(
        self,
        actor: Principal,
        case_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> ActivityPage:
        self.read(actor, case_id)
        if not 1 <= limit <= 100:
            raise InvalidInput("The activity page size is invalid.")
        position = decode_activity_cursor(cursor)
        items, has_more = self.store.list_activity(actor, case_id, position, limit)
        return activity_page(items, has_more)

    async def decide(self, actor: Principal, case_id: UUID, decision: Decision) -> Case:
        case = self.store.get(case_id)
        self.policy.authorize_decision(actor, case)
        self.store.record_decision(case_id, actor, decision)
        await self.host.resume(case_id, actor)
        return self.store.get(case_id)
