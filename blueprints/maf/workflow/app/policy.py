import json
import re
from typing import Any

from .errors import AccessDenied
from .models import Case, Principal


class CaseAccessPolicy:
    """Default owner/assigned-reviewer policy; applications may replace it."""

    def authorize_submission(self, actor: Principal, reviewer_id: str) -> None:
        if (
            "workflow.write" not in actor.scopes
            or not actor.tenant_id
            or not actor.subject
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", reviewer_id)
            or reviewer_id == actor.subject
        ):
            raise AccessDenied("Submission is not authorized.")

    def authorize_read(self, actor: Principal, case: Case) -> None:
        if (
            "workflow.read" not in actor.scopes
            or actor.tenant_id != case.tenant_id
            or actor.subject not in (case.owner_id, case.reviewer_id)
        ):
            raise AccessDenied("Record access is not authorized.")

    def authorize_decision(self, actor: Principal, case: Case) -> None:
        if (
            "workflow.approve" not in actor.scopes
            or "Workflow.Approver" not in actor.roles
            or actor.tenant_id != case.tenant_id
            or actor.subject != case.reviewer_id
            or actor.subject == case.owner_id
        ):
            raise AccessDenied("Decision is not authorized.")


class JsonObjectRules:
    """Bounded, domain-neutral input validation; replace with application rules."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
            raise ValueError("The payload must be a JSON object with string keys.")
        try:
            encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("The payload must contain valid JSON.") from exc
        if len(encoded.encode("utf-8")) > 16_384:
            raise ValueError("The payload exceeds the 16 KiB limit.")
        return json.loads(encoded)
