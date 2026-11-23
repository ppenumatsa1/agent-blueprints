from __future__ import annotations

import threading
from uuid import UUID


ACK_FAULTS = frozenset({"decision-ack-lost", "effect-ack-lost"})


class AcceptanceFaults:
    """Revision-bound, in-memory controls for synthetic acceptance only."""

    def __init__(self, *, enabled: bool, deployment_revision: str) -> None:
        self.enabled = enabled
        self.deployment_revision = deployment_revision
        self._postgres_transient = False
        self._armed: set[tuple[UUID, str]] = set()
        self._observed: set[tuple[UUID, str]] = set()
        self._lock = threading.RLock()

    def authorize_revision(self, deployment_revision: str) -> None:
        if not self.enabled:
            raise PermissionError("Acceptance controls are disabled.")
        if deployment_revision != self.deployment_revision:
            raise PermissionError("Acceptance controls are bound to another deployment.")

    def set_postgres_transient(self, enabled: bool) -> None:
        with self._lock:
            self._postgres_transient = enabled

    def postgres_transient(self) -> bool:
        with self._lock:
            return self._postgres_transient

    def set_ack_fault(self, case_id: UUID, fault: str, enabled: bool) -> None:
        if fault not in ACK_FAULTS:
            raise ValueError("The acceptance fault is not supported.")
        key = (case_id, fault)
        with self._lock:
            if enabled:
                self._armed.add(key)
            else:
                self._armed.discard(key)

    def consume_ack_fault(self, case_id: UUID, operation: str) -> bool:
        fault = {
            "claim-decision": "decision-ack-lost",
            "apply-effect": "effect-ack-lost",
        }.get(operation)
        if fault is None:
            return False
        key = (case_id, fault)
        with self._lock:
            if key not in self._armed:
                return False
            self._armed.remove(key)
            self._observed.add(key)
            return True

    def armed(self, case_id: UUID) -> list[str]:
        with self._lock:
            return sorted(fault for candidate, fault in self._armed if candidate == case_id)

    def observed(self, case_id: UUID) -> list[str]:
        with self._lock:
            return sorted(fault for candidate, fault in self._observed if candidate == case_id)
