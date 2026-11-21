import hashlib
import json
import re
from typing import Any
from uuid import UUID

from app.domain.errors import InvalidInput
from app.domain.models import (
    AccessPolicy,
    BusinessRules,
    Case,
    Decision,
    Principal,
    StateRepository,
    WorkflowHost,
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
        await self.host.start(case.id)
        return self.store.get(case.id)

    def read(self, actor: Principal, case_id: UUID) -> Case:
        case = self.store.get(case_id)
        self.policy.authorize_read(actor, case)
        return case

    async def decide(self, actor: Principal, case_id: UUID, decision: Decision) -> Case:
        case = self.store.get(case_id)
        self.policy.authorize_decision(actor, case)
        self.store.record_decision(case_id, actor, decision)
        await self.host.resume(case_id)
        return self.store.get(case_id)
