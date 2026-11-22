from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

import httpx
from azure.identity import DefaultAzureCredential


FOUNDRY_SCOPE = "https://ai.azure.com/.default"


class OperationStatus(str, Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    request_digest: str
    status: OperationStatus
    remote_id: str | None = None


@dataclass(frozen=True)
class OperationClaim:
    record: OperationRecord
    acquired: bool


class OperationJournal(Protocol):
    def claim(self, operation_id: str, request_digest: str) -> OperationClaim: ...

    def update(self, record: OperationRecord) -> OperationRecord: ...

    def get(self, operation_id: str) -> OperationRecord | None: ...


class MemoryOperationJournal:
    """Test/local journal; production callers must supply durable application storage."""

    def __init__(self) -> None:
        self._records: dict[str, OperationRecord] = {}
        self._lock = threading.RLock()

    def claim(self, operation_id: str, request_digest: str) -> OperationClaim:
        with self._lock:
            existing = self._records.get(operation_id)
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise ValueError("The operation ID is bound to different request content.")
                return OperationClaim(existing, acquired=False)
            record = OperationRecord(operation_id, request_digest, OperationStatus.PENDING)
            self._records[operation_id] = record
            return OperationClaim(record, acquired=True)

    def update(self, record: OperationRecord) -> OperationRecord:
        with self._lock:
            existing = self._records.get(record.operation_id)
            if existing is None or existing.request_digest != record.request_digest:
                raise ValueError("The operation claim is missing or conflicts.")
            if existing.status is OperationStatus.ACKNOWLEDGED:
                if (
                    record.status is OperationStatus.ACKNOWLEDGED
                    and existing.remote_id == record.remote_id
                ):
                    return existing
                raise ValueError("An acknowledged operation cannot change outcome.")
            self._records[record.operation_id] = record
            return record

    def get(self, operation_id: str) -> OperationRecord | None:
        with self._lock:
            return self._records.get(operation_id)


class AmbiguousCreate(RuntimeError):
    """The POST may have applied; callers must reconcile and must not replay it."""


class TokenProvider:
    def __init__(self, credential: Any | None = None) -> None:
        self._credential = credential or DefaultAzureCredential()

    def authorization_header(self) -> str:
        token = self._credential.get_token(FOUNDRY_SCOPE)
        return f"Bearer {token.token}"


@dataclass(frozen=True)
class ConversationBinding:
    caller_id: str
    conversation_id: str
    session_id: str

    def __post_init__(self) -> None:
        for value in (self.caller_id, self.conversation_id, self.session_id):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError("Caller, conversation, and session bindings are required.")


class ResponsesClient:
    """Issue at-most-once-biased Responses creates with explicit reconciliation."""

    def __init__(
        self,
        endpoint: str,
        journal: OperationJournal,
        *,
        conversation_endpoint: str | None = None,
        token_provider: TokenProvider | None = None,
        timeout_seconds: float = 60,
        post: Callable[..., Any] | None = None,
    ) -> None:
        self._endpoint = self._validated_endpoint(endpoint, "Responses")
        self._conversation_endpoint = (
            self._validated_endpoint(conversation_endpoint, "Conversation")
            if conversation_endpoint
            else None
        )
        if timeout_seconds <= 0:
            raise ValueError("The timeout must be positive.")
        self._journal = journal
        self._token_provider = token_provider or TokenProvider()
        self._timeout_seconds = timeout_seconds
        self._post = post or httpx.post

    @staticmethod
    def _validated_endpoint(endpoint: str, label: str) -> str:
        value = endpoint.rstrip("/")
        parsed = urlsplit(value)
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or (
                parsed.scheme != "https"
                and not (
                    parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise ValueError(f"The {label} endpoint must use HTTPS or loopback HTTP.")
        return value

    @staticmethod
    def _digest(endpoint: str, payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            {"endpoint": endpoint, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _post_once(
        self,
        endpoint: str,
        operation_id: str,
        payload: dict[str, Any],
    ) -> str:
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 256:
            raise ValueError("A bounded operation ID is required.")
        digest = self._digest(endpoint, payload)
        claim = self._journal.claim(operation_id, digest)
        record = claim.record
        if record.status is OperationStatus.ACKNOWLEDGED:
            return record.remote_id or ""
        if record.status is OperationStatus.UNKNOWN:
            raise AmbiguousCreate("The operation is unknown and cannot be replayed.")
        if record.status is OperationStatus.REJECTED:
            raise RuntimeError("The operation was previously rejected.")
        if not claim.acquired:
            self._journal.update(replace(record, status=OperationStatus.UNKNOWN))
            raise AmbiguousCreate(
                "The pending operation has no active owner proof and cannot be replayed."
            )
        headers = {
            "Authorization": self._token_provider.authorization_header(),
            "Content-Type": "application/json",
        }
        try:
            response = self._post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
        except Exception:
            self._journal.update(replace(record, status=OperationStatus.UNKNOWN))
            raise AmbiguousCreate("The create acknowledgment was lost; do not retry.") from None
        if response.status_code >= 500:
            self._journal.update(replace(record, status=OperationStatus.UNKNOWN))
            raise AmbiguousCreate("The service error is ambiguous; do not retry the create.")
        if response.status_code >= 400:
            self._journal.update(replace(record, status=OperationStatus.REJECTED))
            response.raise_for_status()
        malformed = object()
        try:
            body = response.json()
        except Exception:
            body = malformed
        if body is malformed:
            self._journal.update(replace(record, status=OperationStatus.UNKNOWN))
            raise AmbiguousCreate(
                "The successful response acknowledgment was malformed; do not retry."
            )
        remote_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(remote_id, str) or not remote_id:
            self._journal.update(replace(record, status=OperationStatus.UNKNOWN))
            raise AmbiguousCreate("The successful response did not contain an authoritative ID.")
        self._journal.update(
            replace(
                record,
                status=OperationStatus.ACKNOWLEDGED,
                remote_id=remote_id,
            )
        )
        return remote_id

    def create_conversation(
        self,
        *,
        operation_id: str,
        caller_id: str,
        session_id: str,
    ) -> ConversationBinding:
        if self._conversation_endpoint is None:
            raise ValueError("An explicit conversation endpoint is required.")
        if not caller_id or not session_id:
            raise ValueError("Caller and session bindings are required.")
        conversation_id = self._post_once(
            self._conversation_endpoint,
            operation_id,
            {
                "metadata": {
                    "operation_id": operation_id,
                    "caller_id": caller_id,
                    "session_id": session_id,
                }
            },
        )
        return ConversationBinding(caller_id, conversation_id, session_id)

    def start(
        self,
        *,
        operation_id: str,
        binding: ConversationBinding,
        case_id: str,
    ) -> str:
        return self._post_once(
            self._endpoint,
            operation_id,
            {
                "agent_session_id": binding.session_id,
                "background": True,
                "conversation": {"id": binding.conversation_id},
                "input": json.dumps({"case_id": case_id}, separators=(",", ":")),
                "metadata": {
                    "operation_id": operation_id,
                    "caller_id": binding.caller_id,
                },
                "store": True,
            },
        )

    def resume(
        self,
        *,
        operation_id: str,
        binding: ConversationBinding,
        request_id: str,
        decision: dict[str, Any],
    ) -> str:
        if (
            decision.get("conversation_id") != binding.conversation_id
            or decision.get("session_id") != binding.session_id
            or decision.get("channel") != "foundry-responses"
            or decision.get("handle") != request_id
        ):
            raise PermissionError("The structured decision does not match the client binding.")
        return self._post_once(
            self._endpoint,
            operation_id,
            {
                "agent_session_id": binding.session_id,
                "background": True,
                "conversation": {"id": binding.conversation_id},
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": request_id,
                        "output": json.dumps(
                            decision,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    }
                ],
                "metadata": {
                    "operation_id": operation_id,
                    "caller_id": binding.caller_id,
                },
                "store": True,
            },
        )

    def reconcile_acknowledgment(
        self,
        operation_id: str,
        authoritative_remote_ids: list[str],
    ) -> OperationRecord:
        record = self._journal.get(operation_id)
        if record is None:
            raise ValueError("The operation was not claimed.")
        candidates = sorted({value for value in authoritative_remote_ids if value})
        if len(candidates) != 1:
            return record
        return self._journal.update(
            replace(
                record,
                status=OperationStatus.ACKNOWLEDGED,
                remote_id=candidates[0],
            )
        )
