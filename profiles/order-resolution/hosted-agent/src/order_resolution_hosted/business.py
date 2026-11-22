from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from azure.identity import DefaultAzureCredential

from .application import CallerContext


PrincipalKind = Literal["owner", "reviewer"]
Outcome = Literal["automatic", "approved", "rejected"]


class AmbiguousBusinessOperation(RuntimeError):
    """The API write may have applied and must not be replayed automatically."""


class ApiTokenProvider:
    def __init__(self, scope: str, credential: Any | None = None) -> None:
        if (
            not isinstance(scope, str)
            or not scope.startswith("api://")
            or not scope.endswith("/.default")
            or any(character.isspace() for character in scope)
            or len(scope) > 512
        ):
            raise ValueError("The internal API scope must use api://.../.default.")
        self._scope = scope
        self._credential = credential or DefaultAzureCredential()

    def authorization_header(self) -> str:
        token = self._credential.get_token(self._scope)
        return f"Bearer {token.token}"


def _encoded(value: Any) -> Any:
    if is_dataclass(value):
        return _encoded(asdict(value))
    if isinstance(value, dict):
        return {str(key): _encoded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_encoded(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("The API datetime is invalid.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise TypeError(f"The internal API {label} contract drifted.")
    return value


class HttpHostedBusinessStore:
    """Authenticated internal API adapter for hosted business and identity state."""

    _CASE_KEYS = {
        "id",
        "tenant_id",
        "owner_id",
        "reviewer_id",
        "payload",
        "status",
        "decision",
        "request_id",
        "execution_complete",
        "failure_code",
    }
    _PROPOSAL_KEYS = {
        "case_id",
        "proposal_version",
        "tenant_id",
        "owner_id",
        "reviewer_id",
        "input_digest",
        "policy_evidence_digest",
        "policy_version",
        "action",
        "destination_id",
        "approval_required",
        "reason_codes",
        "decision_handle_digest",
        "decision_expires_at",
        "decision_channel",
    }
    _DECISION_KEYS = {
        "case_id",
        "proposal_version",
        "action",
        "destination_id",
        "decision",
        "actor_id",
        "tenant_id",
        "scope",
        "channel",
        "decided_at",
    }
    _PRINCIPAL_KEYS = {"tenant_id", "subject", "scopes", "roles"}

    def __init__(
        self,
        endpoint: str,
        token_provider: ApiTokenProvider,
        *,
        timeout_seconds: float = 30,
        request: Callable[..., Any] | None = None,
    ) -> None:
        value = endpoint.rstrip("/")
        parsed = urlsplit(value)
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme != "https"
                and not (
                    parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise ValueError("The internal API endpoint must use HTTPS or loopback HTTP.")
        if timeout_seconds <= 0:
            raise ValueError("The internal API timeout must be positive.")
        self._endpoint = value
        self._token_provider = token_provider
        self._timeout_seconds = timeout_seconds
        self._request = request or httpx.request
        self._unknown_operations: set[str] = set()
        self._lock = threading.RLock()

    @classmethod
    def from_environment(cls) -> "HttpHostedBusinessStore":
        endpoint = os.environ.get("ORDER_RESOLUTION_API_ENDPOINT", "").strip()
        scope = os.environ.get("ORDER_RESOLUTION_API_SCOPE", "").strip()
        try:
            timeout = float(os.environ.get("ORDER_RESOLUTION_API_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise ValueError("ORDER_RESOLUTION_API_TIMEOUT_SECONDS must be numeric.") from exc
        return cls(endpoint, ApiTokenProvider(scope), timeout_seconds=timeout)

    @staticmethod
    def _caller(caller: CallerContext) -> dict[str, str]:
        return {
            "caller_id": caller.user_id,
            "session_id": caller.session_id,
        }

    @staticmethod
    def _binding_operation(label: str, case_id: UUID, *values: str) -> str:
        digest = hashlib.sha256(
            json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:32]
        return f"case:{case_id}:{label}:{digest}"

    def _mark_unknown(self, operation_id: str) -> None:
        with self._lock:
            self._unknown_operations.add(operation_id)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any],
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        if operation_id is not None:
            if not operation_id or len(operation_id) > 256:
                raise ValueError("A bounded internal operation ID is required.")
            with self._lock:
                if operation_id in self._unknown_operations:
                    raise AmbiguousBusinessOperation(
                        "The internal API operation is unknown and cannot be replayed."
                    )
        headers = {
            "Authorization": self._token_provider.authorization_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if operation_id is not None:
            headers["Idempotency-Key"] = operation_id
        try:
            response = self._request(
                method,
                f"{self._endpoint}{path}",
                headers=headers,
                json=_encoded(payload),
                timeout=self._timeout_seconds,
            )
        except (httpx.HTTPError, TimeoutError, OSError):
            if operation_id is not None:
                self._mark_unknown(operation_id)
                raise AmbiguousBusinessOperation(
                    "The internal API acknowledgment was lost; do not retry automatically."
                ) from None
            raise RuntimeError("The internal API read failed.") from None
        if response.status_code >= 500 or response.status_code in {408, 425, 429}:
            if operation_id is not None:
                self._mark_unknown(operation_id)
                raise AmbiguousBusinessOperation(
                    "The internal API write outcome is unknown; do not retry automatically."
                )
            raise RuntimeError("The internal API read failed.")
        if response.status_code >= 400:
            response.raise_for_status()
        if response.status_code < 200 or response.status_code >= 300:
            if operation_id is not None:
                self._mark_unknown(operation_id)
                raise AmbiguousBusinessOperation(
                    "The internal API write did not return an authoritative acknowledgment."
                )
            response.raise_for_status()
        try:
            body = response.json()
        except (TypeError, ValueError):
            if operation_id is not None:
                self._mark_unknown(operation_id)
                raise AmbiguousBusinessOperation(
                    "The internal API write acknowledgment was malformed."
                ) from None
            raise RuntimeError("The internal API read response was malformed.") from None
        if not isinstance(body, dict):
            if operation_id is not None:
                self._mark_unknown(operation_id)
                raise AmbiguousBusinessOperation(
                    "The internal API write acknowledgment was malformed."
                )
            raise RuntimeError("The internal API read response was malformed.")
        return body

    def for_binding(
        self,
        caller: CallerContext,
        conversation_id: str,
        principal_kind: PrincipalKind,
    ) -> "_BoundBusinessStore":
        return _BoundBusinessStore(self, caller, conversation_id, principal_kind)

    def resolve_principal(self, _caller: CallerContext) -> Any:
        raise RuntimeError("The principal must be resolved by a case-bound API operation.")

    def _principal(self, body: dict[str, Any]) -> Any:
        from app.domain.models import Principal

        value = _exact(body, self._PRINCIPAL_KEYS, "principal")
        return Principal(
            tenant_id=value["tenant_id"],
            subject=value["subject"],
            scopes=frozenset(value["scopes"]),
            roles=frozenset(value["roles"]),
        )

    def bind_start(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
    ) -> Any:
        operation_id = self._binding_operation(
            "bind-start",
            case_id,
            caller.user_id,
            caller.session_id,
            conversation_id,
        )
        return self._principal(
            self._request_json(
                "POST",
                f"/cases/{case_id}/bindings/start",
                payload={
                    **self._caller(caller),
                    "conversation_id": conversation_id,
                    "channel": "foundry-responses",
                },
                operation_id=operation_id,
            )
        )

    def authorize_resume(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
        channel: str,
    ) -> Any:
        operation_id = self._binding_operation(
            "bind-resume",
            case_id,
            caller.user_id,
            caller.session_id,
            conversation_id,
            channel,
        )
        return self._principal(
            self._request_json(
                "POST",
                f"/cases/{case_id}/bindings/resume",
                payload={
                    **self._caller(caller),
                    "conversation_id": conversation_id,
                    "channel": channel,
                },
                operation_id=operation_id,
            )
        )

    def _case(self, body: dict[str, Any]) -> Any:
        from app.domain.models import Case

        value = _exact(body, self._CASE_KEYS, "case")
        return Case(
            id=UUID(value["id"]),
            tenant_id=value["tenant_id"],
            owner_id=value["owner_id"],
            reviewer_id=value["reviewer_id"],
            payload=value["payload"],
            status=value["status"],
            decision=value["decision"],
            request_id=value["request_id"],
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=value["execution_complete"],
            failure_code=value["failure_code"],
        )

    def _proposal(self, body: dict[str, Any]) -> Any:
        from app.order_resolution.durability import Proposal

        value = _exact(body, self._PROPOSAL_KEYS, "proposal")
        return Proposal(
            **(
                value
                | {
                    "reason_codes": tuple(value["reason_codes"]),
                    "decision_expires_at": _datetime(value["decision_expires_at"]),
                }
            )
        )

    def _decision(self, body: dict[str, Any]) -> Any:
        from app.order_resolution.durability import Decision, DecisionRecord

        value = _exact(body, self._DECISION_KEYS, "decision")
        return DecisionRecord(
            **(
                value
                | {
                    "decision": Decision(value["decision"]),
                    "decided_at": _datetime(value["decided_at"]),
                }
            )
        )


class _BoundBusinessStore:
    def __init__(
        self,
        api: HttpHostedBusinessStore,
        caller: CallerContext,
        conversation_id: str,
        principal_kind: PrincipalKind,
    ) -> None:
        self._api = api
        self._caller = caller
        self._conversation_id = conversation_id
        self._principal_kind = principal_kind
        self._outcome: Outcome | None = None

    def _binding(self) -> dict[str, str]:
        return {
            **self._api._caller(self._caller),
            "conversation_id": self._conversation_id,
            "channel": "foundry-responses",
        }

    def get(self, case_id: UUID) -> Any:
        return self._api._case(
            self._api._request_json(
                "POST",
                f"/cases/{case_id}/read",
                payload={
                    **self._binding(),
                    "principal_kind": self._principal_kind,
                },
            )
        )

    def prepare_hosted_approval(
        self,
        case_id: UUID,
        candidate_request_id: str,
        *,
        channel: str,
    ) -> Any:
        return self._api._proposal(
            self._api._request_json(
                "POST",
                f"/cases/{case_id}/approvals/prepare",
                payload={
                    **self._binding(),
                    "channel": channel,
                    "request_id": candidate_request_id,
                },
                operation_id=f"case:{case_id}:approval:{candidate_request_id}",
            )
        )

    def get_current_proposal(self, case_id: str) -> Any:
        value = UUID(case_id)
        return self._api._proposal(
            self._api._request_json(
                "POST",
                f"/cases/{value}/proposal/read",
                payload={
                    **self._binding(),
                    "principal_kind": self._principal_kind,
                },
            )
        )

    def record_hosted_decision(self, command: Any) -> Any:
        case_id = UUID(command.case_id)
        return self._api._decision(
            self._api._request_json(
                "POST",
                f"/cases/{case_id}/decisions/claim",
                payload={
                    **self._binding(),
                    "proposal_version": command.proposal_version,
                    "action": command.action,
                    "destination_id": command.destination_id,
                    "handle": command.handle,
                    "decision": _encoded(command.decision),
                },
                operation_id=(
                    f"case:{case_id}:decision:{command.proposal_version}:"
                    f"{_encoded(command.decision)}"
                ),
            )
        )

    def claim_hosted_decision(self, _decision: Any) -> Any:
        raise RuntimeError("HTTP decisions must be claimed from the bound command.")

    def apply_automatic(self, case_id: UUID, _action: Any) -> None:
        self._outcome = "automatic"
        self._apply(case_id)

    def apply_once(self, case_id: UUID, approved: bool, _action: Any) -> None:
        self._outcome = "approved" if approved else "rejected"
        self._apply(case_id)

    def _apply(self, case_id: UUID) -> None:
        assert self._outcome is not None
        self._api._case(
            self._api._request_json(
                "POST",
                f"/cases/{case_id}/effects/apply",
                payload={
                    **self._binding(),
                    "mode": self._outcome,
                },
                operation_id=f"case:{case_id}:action:{self._outcome}",
            )
        )

    def finish_hosted(self, case_id: UUID) -> None:
        if self._outcome is None:
            raise RuntimeError("The hosted action must be applied before completion.")
        self._api._case(
            self._api._request_json(
                "POST",
                f"/cases/{case_id}/finish",
                payload={
                    **self._binding(),
                    "mode": self._outcome,
                },
                operation_id=f"case:{case_id}:completion:{self._outcome}",
            )
        )
