"""Application records that correlate with, but never replace, native MAF checkpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, Sequence
from uuid import UUID


_SAFE_ID = re.compile(r"[A-Za-z0-9._:@/-]{1,256}")
DECISION_SCOPE = "workflow.approve"


class DurabilityError(RuntimeError):
    """Base class for explicit fail-closed durability errors."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AuthorizationDenied(DurabilityError):
    pass


class Conflict(DurabilityError):
    pass


class EvidenceIntegrityError(DurabilityError):
    pass


class Decision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DurabilityError("invalid_json", "The value is not canonical JSON.") from exc


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceIntegrityError(
            "policy_evidence_invalid", "Evidence timestamps must include an offset."
        )
    return value.astimezone(timezone.utc)


def _safe(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise DurabilityError("invalid_identity", f"{label} is invalid.")
    return value


def _case_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise DurabilityError("invalid_identity", "Case identity must be a UUID.") from exc
    return str(parsed)


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    subject: str
    scopes: frozenset[str]
    roles: frozenset[str]


@dataclass(frozen=True)
class RequestClaim:
    tenant_id: str
    owner_id: str
    request_key: str
    request_digest: str
    case_id: str

    def __post_init__(self) -> None:
        _safe(self.tenant_id, "Tenant identity")
        _safe(self.owner_id, "Owner identity")
        _safe(self.request_key, "Request identity")
        _case_id(self.case_id)
        if not re.fullmatch(r"[0-9a-f]{64}", self.request_digest):
            raise DurabilityError("invalid_digest", "The request digest is invalid.")


class RequestStore(Protocol):
    def claim_request(self, claim: RequestClaim) -> RequestClaim:
        """Atomically return the matching existing claim or persist this claim."""
        ...


def claim_request(store: RequestStore, claim: RequestClaim) -> RequestClaim:
    existing = store.claim_request(claim)
    if existing != claim:
        if (
            existing.tenant_id == claim.tenant_id
            and existing.owner_id == claim.owner_id
            and existing.request_key == claim.request_key
            and existing.request_digest == claim.request_digest
        ):
            return existing
        raise Conflict(
            "request_identity_conflict",
            "The request identity is already bound to different content.",
        )
    return existing


@dataclass(frozen=True)
class PolicyEvidence:
    evidence_id: str
    policy_version: str
    action: str
    approval_required: bool
    applicable: bool
    retrieved_at: datetime
    expires_at: datetime
    digest: str

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "applicable": self.applicable,
            "approval_required": self.approval_required,
            "evidence_id": self.evidence_id,
            "expires_at": _utc(self.expires_at).isoformat(),
            "policy_version": self.policy_version,
            "retrieved_at": _utc(self.retrieved_at).isoformat(),
        }

    def expected_digest(self) -> str:
        return sha256_hex(canonical_json_bytes(self.unsigned_payload()))


def policy_evidence_digest(items: Sequence[PolicyEvidence], *, now: datetime) -> str:
    if not items:
        raise EvidenceIntegrityError(
            "policy_evidence_missing", "Current policy evidence is required."
        )
    if len(items) != 1:
        outcomes = {
            (item.policy_version, item.action, item.approval_required, item.applicable)
            for item in items
        }
        code = "policy_evidence_conflict" if len(outcomes) > 1 else "policy_evidence_invalid"
        raise EvidenceIntegrityError(code, "Exactly one policy evidence set is required.")

    item = items[0]
    for value, label in (
        (item.evidence_id, "Evidence identity"),
        (item.policy_version, "Policy version"),
        (item.action, "Action identity"),
    ):
        try:
            _safe(value, label)
        except DurabilityError as exc:
            raise EvidenceIntegrityError("policy_evidence_invalid", str(exc)) from exc
    current = _utc(now)
    retrieved = _utc(item.retrieved_at)
    expires = _utc(item.expires_at)
    if (
        not item.applicable
        or retrieved > current
        or expires <= current
        or not hmac.compare_digest(item.expected_digest(), item.digest)
    ):
        raise EvidenceIntegrityError(
            "policy_evidence_invalid",
            "Policy evidence is inapplicable, stale, future-dated, or digest-invalid.",
        )
    return sha256_hex(canonical_json_bytes([item.unsigned_payload()]))


@dataclass(frozen=True)
class Proposal:
    case_id: str
    proposal_version: int
    tenant_id: str
    owner_id: str
    reviewer_id: str
    input_digest: str
    policy_evidence_digest: str
    policy_version: str
    action: str
    destination_id: str
    approval_required: bool
    reason_codes: tuple[str, ...]
    decision_handle_digest: str | None
    decision_expires_at: datetime | None
    decision_channel: str | None

    def __post_init__(self) -> None:
        _case_id(self.case_id)
        for value, label in (
            (self.tenant_id, "Tenant identity"),
            (self.owner_id, "Owner identity"),
            (self.reviewer_id, "Reviewer identity"),
            (self.policy_version, "Policy version"),
            (self.action, "Action identity"),
            (self.destination_id, "Destination identity"),
        ):
            _safe(value, label)
        if self.proposal_version < 1:
            raise DurabilityError("invalid_proposal_version", "Proposal version must be positive.")
        if not self.reason_codes or any(not _SAFE_ID.fullmatch(code) for code in self.reason_codes):
            raise DurabilityError("invalid_reason_codes", "Reason codes are required and bounded.")
        for digest in (self.input_digest, self.policy_evidence_digest):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise DurabilityError("invalid_digest", "A proposal digest is invalid.")
        if self.approval_required:
            bindings = (
                self.decision_handle_digest,
                self.decision_expires_at,
                self.decision_channel,
            )
            if any(value is not None for value in bindings) and not all(
                value is not None for value in bindings
            ):
                raise DurabilityError(
                    "invalid_approval_binding",
                    "Approval bindings must set handle, expiry, and channel together.",
                )
            if self.decision_handle_digest is not None:
                if not re.fullmatch(r"[0-9a-f]{64}", self.decision_handle_digest):
                    raise DurabilityError(
                        "invalid_approval_binding",
                        "The decision handle digest is invalid.",
                    )
                _safe(self.decision_channel or "", "Decision channel")
        elif any(
            value is not None
            for value in (
                self.decision_handle_digest,
                self.decision_expires_at,
                self.decision_channel,
            )
        ):
            raise DurabilityError(
                "invalid_approval_binding",
                "Automatic proposals cannot carry a decision binding.",
            )

    @property
    def action_identity(self) -> tuple[str, int, str, str]:
        return (self.case_id, self.proposal_version, self.action, self.destination_id)

    @property
    def submission_identity(self) -> tuple[object, ...]:
        return (
            self.case_id,
            self.proposal_version,
            self.tenant_id,
            self.owner_id,
            self.reviewer_id,
            self.input_digest,
            self.policy_evidence_digest,
            self.policy_version,
            self.action,
            self.destination_id,
            self.approval_required,
            self.reason_codes,
        )


def build_proposal(
    *,
    case_id: str,
    proposal_version: int,
    tenant_id: str,
    owner_id: str,
    reviewer_id: str,
    normalized_input: dict[str, Any],
    evidence: Sequence[PolicyEvidence],
    destination_id: str,
    reason_codes: Sequence[str],
    now: datetime,
    decision_handle: str | None = None,
    decision_expires_at: datetime | None = None,
    decision_channel: str | None = None,
) -> Proposal:
    evidence_digest = policy_evidence_digest(evidence, now=now)
    item = evidence[0]
    handle_digest = sha256_hex(decision_handle.encode("utf-8")) if decision_handle else None
    return Proposal(
        case_id=case_id,
        proposal_version=proposal_version,
        tenant_id=tenant_id,
        owner_id=owner_id,
        reviewer_id=reviewer_id,
        input_digest=sha256_hex(canonical_json_bytes(normalized_input)),
        policy_evidence_digest=evidence_digest,
        policy_version=item.policy_version,
        action=item.action,
        destination_id=destination_id,
        approval_required=item.approval_required,
        reason_codes=tuple(reason_codes),
        decision_handle_digest=handle_digest,
        decision_expires_at=decision_expires_at,
        decision_channel=decision_channel,
    )


@dataclass(frozen=True)
class DecisionCommand:
    case_id: str
    proposal_version: int
    action: str
    destination_id: str
    handle: str
    decision: Decision
    scope: str
    channel: str


@dataclass(frozen=True)
class DecisionRecord:
    case_id: str
    proposal_version: int
    action: str
    destination_id: str
    decision: Decision
    actor_id: str
    tenant_id: str
    scope: str
    channel: str
    decided_at: datetime

    @property
    def action_identity(self) -> tuple[str, int, str, str]:
        return (self.case_id, self.proposal_version, self.action, self.destination_id)


class DecisionStore(Protocol):
    def get_current_proposal(self, case_id: str) -> Proposal:
        """Return the one authoritative current proposal."""
        ...

    def claim_decision(self, decision: DecisionRecord) -> DecisionRecord:
        """Atomically claim approval or rejection, returning an identical duplicate."""
        ...


def record_decision(
    store: DecisionStore,
    proposal: Proposal,
    actor: Actor,
    command: DecisionCommand,
    *,
    now: datetime,
    protected_self_decision: bool = False,
) -> DecisionRecord:
    current = store.get_current_proposal(proposal.case_id)
    if current != proposal:
        raise Conflict("proposal_not_current", "The proposal is no longer current.")
    if not proposal.approval_required:
        raise Conflict("approval_not_required", "This proposal does not accept a decision.")
    if (
        proposal.decision_handle_digest is None
        or proposal.decision_expires_at is None
        or proposal.decision_channel is None
    ):
        raise Conflict(
            "approval_not_ready",
            "The native approval pause has not been durably bound.",
        )
    if (
        DECISION_SCOPE not in actor.scopes
        or "Workflow.Approver" not in actor.roles
        or actor.tenant_id != proposal.tenant_id
        or actor.subject != proposal.reviewer_id
        or (actor.subject == proposal.owner_id and not protected_self_decision)
        or command.scope != DECISION_SCOPE
    ):
        raise AuthorizationDenied("authorization_denied", "Decision is not authorized.")
    if (
        command.case_id != proposal.case_id
        or command.proposal_version != proposal.proposal_version
        or command.action != proposal.action
        or command.destination_id != proposal.destination_id
        or command.channel != proposal.decision_channel
        or not hmac.compare_digest(
            sha256_hex(command.handle.encode("utf-8")),
            proposal.decision_handle_digest or "",
        )
    ):
        raise AuthorizationDenied(
            "authorization_denied",
            "Decision identity does not match the pending proposal.",
        )
    if _utc(now) >= _utc(proposal.decision_expires_at):
        raise AuthorizationDenied("authorization_denied", "Decision authorization has expired.")

    requested = DecisionRecord(
        case_id=proposal.case_id,
        proposal_version=proposal.proposal_version,
        action=proposal.action,
        destination_id=proposal.destination_id,
        decision=command.decision,
        actor_id=actor.subject,
        tenant_id=actor.tenant_id,
        scope=command.scope,
        channel=command.channel,
        decided_at=_utc(now),
    )
    recorded = store.claim_decision(requested)
    if recorded != requested:
        stable_fields = (
            "case_id",
            "proposal_version",
            "action",
            "destination_id",
            "decision",
            "actor_id",
            "tenant_id",
            "scope",
            "channel",
        )
        if all(getattr(recorded, field) == getattr(requested, field) for field in stable_fields):
            return recorded
        raise Conflict(
            "decision_conflict",
            "A different or conflicting decision has already been recorded.",
        )
    return recorded


def require_action_authorization(
    proposal: Proposal,
    current: Proposal,
    decision: DecisionRecord | None,
    *,
    protected_self_decision: bool = False,
) -> None:
    if current != proposal:
        raise Conflict("proposal_not_current", "The proposal is no longer current.")
    if not proposal.approval_required:
        if decision is not None:
            raise Conflict("unexpected_decision", "Automatic action has an unexpected decision.")
        return
    if (
        decision is None
        or decision.decision is not Decision.APPROVED
        or decision.action_identity != proposal.action_identity
        or decision.tenant_id != proposal.tenant_id
        or decision.actor_id != proposal.reviewer_id
        or (decision.actor_id == proposal.owner_id and not protected_self_decision)
        or decision.scope != DECISION_SCOPE
        or decision.channel != proposal.decision_channel
    ):
        raise AuthorizationDenied(
            "authorization_denied",
            "A current, authorized approval is required for this exact action.",
        )
