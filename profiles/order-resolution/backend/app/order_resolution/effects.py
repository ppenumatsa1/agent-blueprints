"""Idempotent effect reconciliation for an application-owned Order Resolution ledger."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from .durability import (
    Conflict,
    DecisionRecord,
    Proposal,
    canonical_json_bytes,
    require_action_authorization,
    sha256_hex,
)


DEFAULT_DOWNSTREAM_DEADLINE_SECONDS = 5.0


class Observation(str, Enum):
    ABSENT = "absent"
    APPLIED = "applied"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class EffectStatus(str, Enum):
    CLAIMED = "claimed"
    UNKNOWN = "unknown"
    VERIFIED = "verified"


class OutcomeUnknown(RuntimeError):
    """The operation may have applied and must be observed before any retry."""


@dataclass(frozen=True)
class EffectIdentity:
    case_id: str
    proposal_version: int
    action: str
    destination_id: str

    @classmethod
    def from_proposal(cls, proposal: Proposal) -> "EffectIdentity":
        return cls(*proposal.action_identity)

    @property
    def key(self) -> str:
        digest = sha256_hex(
            canonical_json_bytes(
                {
                    "action": self.action,
                    "case_id": self.case_id,
                    "destination_id": self.destination_id,
                    "proposal_version": self.proposal_version,
                }
            )
        )
        return f"order-resolution:{digest}"


@dataclass(frozen=True)
class EffectRequest:
    identity: EffectIdentity
    key: str
    digest: str
    body: bytes

    @classmethod
    def create(cls, proposal: Proposal, payload: dict[str, Any]) -> "EffectRequest":
        identity = EffectIdentity.from_proposal(proposal)
        body = canonical_json_bytes(
            {
                "action": proposal.action,
                "case_id": proposal.case_id,
                "destination_id": proposal.destination_id,
                "payload": payload,
                "proposal_version": proposal.proposal_version,
            }
        )
        return cls(identity, identity.key, sha256_hex(body), body)


@dataclass(frozen=True)
class EffectLedgerRecord:
    request: EffectRequest
    status: EffectStatus
    result_digest: str | None = None


class EffectLedger(Protocol):
    def claim_effect(self, request: EffectRequest) -> EffectLedgerRecord:
        """Atomically bind the complete effect identity, key, digest, and body."""
        ...

    def mark_effect_unknown(self, request: EffectRequest) -> None:
        """Record that absence is not established; never downgrade VERIFIED."""
        ...

    def mark_effect_verified(self, request: EffectRequest, result_digest: str) -> None:
        """Persist the result idempotently; reject any conflicting verified digest."""
        ...


class IdempotentDestination(Protocol):
    def observe(self, request: EffectRequest, *, timeout_seconds: float) -> Observation:
        """Return authoritative APPLIED/ABSENT or fail closed with UNKNOWN/CONFLICT."""
        ...

    def send(self, request: EffectRequest, *, timeout_seconds: float) -> None:
        """Atomically bind the key and request digest to one downstream effect."""
        ...


class EffectCoordinator:
    """Reconcile before send and share one bounded deadline across downstream calls."""

    def __init__(
        self,
        ledger: EffectLedger,
        destination: IdempotentDestination,
        *,
        deadline_seconds: float = DEFAULT_DOWNSTREAM_DEADLINE_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        if deadline_seconds <= 0:
            raise ValueError("The downstream deadline must be positive.")
        self._ledger = ledger
        self._destination = destination
        self._deadline_seconds = deadline_seconds
        self._monotonic = monotonic

    def apply(
        self,
        proposal: Proposal,
        current_proposal: Proposal,
        decision: DecisionRecord | None,
        payload: dict[str, Any],
        *,
        protected_self_decision: bool = False,
    ) -> EffectRequest:
        require_action_authorization(
            proposal,
            current_proposal,
            decision,
            protected_self_decision=protected_self_decision,
        )
        request = EffectRequest.create(proposal, payload)
        record = self._ledger.claim_effect(request)
        if record.request != request:
            raise Conflict(
                "effect_identity_conflict",
                "The effect identity is already bound to different content.",
            )
        if record.status is EffectStatus.VERIFIED:
            return request

        deadline = self._monotonic() + self._deadline_seconds

        def remaining() -> float:
            value = deadline - self._monotonic()
            if value <= 0:
                raise TimeoutError("The shared downstream deadline expired.")
            return value

        try:
            observation = self._destination.observe(request, timeout_seconds=remaining())
            remaining()
        except Exception:
            self._ledger.mark_effect_unknown(request)
            raise
        if observation is Observation.APPLIED:
            self._ledger.mark_effect_verified(request, request.digest)
            return request
        if observation is not Observation.ABSENT:
            self._ledger.mark_effect_unknown(request)
            raise OutcomeUnknown("The downstream outcome is not authoritatively absent.")

        try:
            self._destination.send(request, timeout_seconds=remaining())
            remaining()
        except Exception as exc:
            self._ledger.mark_effect_unknown(request)
            raise OutcomeUnknown(
                "The downstream send may have applied; observe before retry."
            ) from exc

        try:
            observation = self._destination.observe(request, timeout_seconds=remaining())
            remaining()
        except Exception as exc:
            self._ledger.mark_effect_unknown(request)
            raise OutcomeUnknown(
                "The downstream acknowledgment could not be authoritatively reconciled."
            ) from exc
        if observation is not Observation.APPLIED:
            self._ledger.mark_effect_unknown(request)
            raise OutcomeUnknown("The downstream result is not verified.")
        self._ledger.mark_effect_verified(request, request.digest)
        return request


class SyntheticIdempotentDestination:
    """Thread-safe synthetic adapter; it is not evidence for a real downstream guarantee."""

    def __init__(self):
        self._lock = threading.Lock()
        self._bindings: dict[str, tuple[str, bytes]] = {}
        self._effects: dict[str, str] = {}
        self.force_unknown = False
        self.timeout_after_send_once = False
        self.timeouts: list[float] = []

    def observe(self, request: EffectRequest, *, timeout_seconds: float) -> Observation:
        self.timeouts.append(timeout_seconds)
        if self.force_unknown:
            return Observation.UNKNOWN
        with self._lock:
            binding = self._bindings.get(request.key)
            effect = self._effects.get(request.key)
        if binding is None:
            return Observation.UNKNOWN if effect is not None else Observation.ABSENT
        if binding != (request.digest, request.body):
            return Observation.CONFLICT
        if effect != hashlib.sha256(request.body).hexdigest():
            return Observation.UNKNOWN
        return Observation.APPLIED

    def send(self, request: EffectRequest, *, timeout_seconds: float) -> None:
        self.timeouts.append(timeout_seconds)
        if timeout_seconds <= 0:
            raise TimeoutError("The downstream deadline expired.")
        if sha256_hex(request.body) != request.digest:
            raise Conflict("effect_digest_invalid", "The request digest does not match its body.")
        with self._lock:
            existing = self._bindings.setdefault(request.key, (request.digest, request.body))
            if existing != (request.digest, request.body):
                raise Conflict(
                    "effect_identity_conflict",
                    "The downstream key is bound to different content.",
                )
            self._effects.setdefault(request.key, request.digest)
        if self.timeout_after_send_once:
            self.timeout_after_send_once = False
            raise TimeoutError("The synthetic acknowledgment timed out after applying the effect.")

    def effect_count(self) -> int:
        with self._lock:
            return len(self._effects)
