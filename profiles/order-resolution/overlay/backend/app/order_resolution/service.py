import hashlib
import json
import re
from typing import Any

from app.domain.errors import InvalidInput
from app.domain.models import Case, Principal
from app.order_resolution.persistence import OrderResolutionStore
from app.usecases.service import WorkflowService


class OrderResolutionService(WorkflowService):
    """Persist authoritative policy failures instead of fabricating a proposal."""

    store: OrderResolutionStore

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
        await self.host.start(case.id)
        return self.store.get(case.id)
