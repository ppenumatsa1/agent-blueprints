"""Opt-in application pattern; adapters and their guarantees are trusted."""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from psycopg import Connection

from app.domain.models import Case


class Observation(Enum):
    ABSENT = "absent"
    APPLIED = "applied"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class EffectRequest:
    key: str
    digest: str
    body: bytes


class Authorizer(Protocol):
    def authorize(self, connection: Connection, case: Case, request: EffectRequest) -> bool:
        """Return True only when this exact approved effect is authorized."""
        ...


class IdempotentDestination(Protocol):
    def observe(self, request: EffectRequest) -> Observation:
        """Return authoritative, request-bound status; UNKNOWN is not ABSENT."""
        ...

    def send(self, request: EffectRequest) -> None:
        """Atomically bind key to digest and effect; reject conflicting reuse."""
        ...


class ExternalEffectAction:
    """Use only with a verified durable, atomic downstream idempotency contract."""

    def __init__(
        self,
        authorizer: Authorizer,
        destination: IdempotentDestination,
        *,
        operation: str,
        destination_id: str,
    ):
        if not operation or not destination_id:
            raise ValueError("A stable operation and destination identity are required.")
        self.authorizer = authorizer
        self.destination = destination
        self.operation = operation
        self.destination_id = destination_id

    def apply(self, connection: Connection, case: Case) -> None:
        if case.decision != "approved":
            raise RuntimeError("An approved decision is required.")
        body = json.dumps(
            {
                "case_id": str(case.id),
                "tenant_id": case.tenant_id,
                "owner_id": case.owner_id,
                "reviewer_id": case.reviewer_id,
                "operation": self.operation,
                "destination_id": self.destination_id,
                "payload": case.payload,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        request = EffectRequest(
            key=f"case:{case.id}:action",
            digest=hashlib.sha256(body).hexdigest(),
            body=body,
        )
        if self.authorizer.authorize(connection, case, request) is not True:
            raise RuntimeError("External effect is not authorized.")
        observation = self.destination.observe(request)
        if observation is Observation.APPLIED:
            return
        if observation is not Observation.ABSENT:
            raise RuntimeError("External effect could not be safely reconciled.")
        self.destination.send(request)
        if self.destination.observe(request) is not Observation.APPLIED:
            raise RuntimeError("External effect acknowledgment could not be verified.")
