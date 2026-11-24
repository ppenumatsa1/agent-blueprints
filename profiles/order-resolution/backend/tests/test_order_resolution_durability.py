from __future__ import annotations

import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.order_resolution.durability import (  # noqa: E402
    Actor,
    AuthorizationDenied,
    Conflict,
    Decision,
    DecisionCommand,
    DecisionRecord,
    EvidenceIntegrityError,
    PolicyEvidence,
    Proposal,
    RequestClaim,
    build_proposal,
    claim_request,
    record_decision,
)
from app.order_resolution.effects import (  # noqa: E402
    EffectCoordinator,
    EffectLedgerRecord,
    EffectRequest,
    EffectStatus,
    OutcomeUnknown,
    SyntheticIdempotentDestination,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CASE_ID = "00000000-0000-0000-0000-000000000001"
OTHER_CASE_ID = "00000000-0000-0000-0000-000000000002"


def evidence(**changes):
    item = PolicyEvidence(
        evidence_id="POLICY-LATE@1",
        policy_version="POLICY-LATE@1",
        action="partial_refund_10",
        approval_required=True,
        applicable=True,
        retrieved_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        digest="",
    )
    item = replace(item, digest=item.expected_digest())
    return replace(item, **changes)


def proposal(**changes):
    value = build_proposal(
        case_id=CASE_ID,
        proposal_version=1,
        tenant_id="tenant-1",
        owner_id="USER-A",
        reviewer_id="REVIEWER-A",
        normalized_input={"amount": "185.00", "issue": "late_delivery"},
        evidence=[evidence()],
        destination_id="refund-api",
        reason_codes=["late_over_3_days", "approval_threshold"],
        now=NOW,
        decision_handle="opaque-handle",
        decision_expires_at=NOW + timedelta(minutes=10),
        decision_channel="web",
    )
    return replace(value, **changes)


def actor(**changes):
    value = Actor(
        tenant_id="tenant-1",
        subject="REVIEWER-A",
        scopes=frozenset({"workflow.approve"}),
        roles=frozenset({"Workflow.Approver"}),
    )
    return replace(value, **changes)


def command(**changes):
    value = DecisionCommand(
        case_id=CASE_ID,
        proposal_version=1,
        action="partial_refund_10",
        destination_id="refund-api",
        handle="opaque-handle",
        decision=Decision.APPROVED,
        scope="workflow.approve",
        channel="web",
    )
    return replace(value, **changes)


class MemoryStore:
    def __init__(self, current: Proposal):
        self.current = current
        self.requests = {}
        self.decisions = {}
        self.effects = {}
        self.lock = threading.Lock()

    def claim_request(self, request):
        key = (request.tenant_id, request.owner_id, request.request_key)
        with self.lock:
            return self.requests.setdefault(key, request)

    def get_current_proposal(self, case_id):
        if self.current.case_id != case_id:
            raise KeyError(case_id)
        return self.current

    def claim_decision(self, decision):
        key = (decision.case_id, decision.proposal_version)
        with self.lock:
            return self.decisions.setdefault(key, decision)

    def claim_effect(self, request):
        key = request.identity
        with self.lock:
            return self.effects.setdefault(
                key, EffectLedgerRecord(request=request, status=EffectStatus.CLAIMED)
            )

    def mark_effect_unknown(self, request):
        with self.lock:
            current = self.effects[request.identity]
            if current.request != request:
                raise Conflict("effect_identity_conflict", "Conflicting effect request.")
            if current.status is EffectStatus.VERIFIED:
                return
            self.effects[request.identity] = EffectLedgerRecord(
                request=request, status=EffectStatus.UNKNOWN
            )

    def mark_effect_verified(self, request, result_digest):
        with self.lock:
            current = self.effects[request.identity]
            if current.request != request:
                raise Conflict("effect_identity_conflict", "Conflicting effect request.")
            if current.status is EffectStatus.VERIFIED and current.result_digest != result_digest:
                raise Conflict("effect_result_conflict", "Conflicting verified effect result.")
            self.effects[request.identity] = EffectLedgerRecord(
                request=request,
                status=EffectStatus.VERIFIED,
                result_digest=result_digest,
            )


class EvidenceTests(unittest.TestCase):
    def test_missing_conflicting_and_invalid_evidence_fail_closed(self):
        with self.assertRaisesRegex(EvidenceIntegrityError, "required") as missing:
            build_proposal(
                case_id=CASE_ID,
                proposal_version=1,
                tenant_id="tenant-1",
                owner_id="USER-A",
                reviewer_id="REVIEWER-A",
                normalized_input={},
                evidence=[],
                destination_id="refund-api",
                reason_codes=["reason"],
                now=NOW,
            )
        self.assertEqual(missing.exception.code, "policy_evidence_missing")

        with self.assertRaises(EvidenceIntegrityError) as conflicting:
            build_proposal(
                case_id=CASE_ID,
                proposal_version=1,
                tenant_id="tenant-1",
                owner_id="USER-A",
                reviewer_id="REVIEWER-A",
                normalized_input={},
                evidence=[evidence(), evidence(action="replacement_shipment")],
                destination_id="refund-api",
                reason_codes=["reason"],
                now=NOW,
            )
        self.assertEqual(conflicting.exception.code, "policy_evidence_conflict")

        for item in (
            evidence(digest="0" * 64),
            evidence(applicable=False),
            evidence(expires_at=NOW),
        ):
            with self.subTest(item=item):
                with self.assertRaises(EvidenceIntegrityError) as invalid:
                    build_proposal(
                        case_id=CASE_ID,
                        proposal_version=1,
                        tenant_id="tenant-1",
                        owner_id="USER-A",
                        reviewer_id="REVIEWER-A",
                        normalized_input={},
                        evidence=[item],
                        destination_id="refund-api",
                        reason_codes=["reason"],
                        now=NOW,
                    )
                self.assertEqual(invalid.exception.code, "policy_evidence_invalid")


class RequestAndDecisionTests(unittest.TestCase):
    def setUp(self):
        self.proposal = proposal()
        self.store = MemoryStore(self.proposal)

    def test_duplicate_request_returns_original_and_changed_content_conflicts(self):
        first = RequestClaim("tenant-1", "USER-A", "request-1", "a" * 64, CASE_ID)
        self.assertEqual(claim_request(self.store, first), first)
        self.assertEqual(claim_request(self.store, first), first)
        with self.assertRaises(Conflict):
            claim_request(
                self.store,
                RequestClaim("tenant-1", "USER-A", "request-1", "b" * 64, OTHER_CASE_ID),
            )

    def test_decision_is_bound_to_actor_proposal_action_handle_channel_and_expiry(self):
        for bad_actor, bad_command, now in (
            (actor(subject="REVIEWER-B"), command(), NOW),
            (actor(tenant_id="tenant-2"), command(), NOW),
            (actor(scopes=frozenset()), command(), NOW),
            (actor(roles=frozenset()), command(), NOW),
            (actor(), command(proposal_version=2), NOW),
            (actor(), command(action="replacement_shipment"), NOW),
            (actor(), command(handle="forged"), NOW),
            (actor(), command(channel="email"), NOW),
            (actor(), command(), NOW + timedelta(hours=1)),
        ):
            with self.subTest(actor=bad_actor, command=bad_command, now=now):
                with self.assertRaises(AuthorizationDenied):
                    record_decision(self.store, self.proposal, bad_actor, bad_command, now=now)
        self.assertEqual(self.store.decisions, {})

    def test_owner_cannot_decide_even_when_assigned_and_fully_privileged(self):
        same_identity = replace(self.proposal, reviewer_id=self.proposal.owner_id)
        store = MemoryStore(same_identity)
        for value in (Decision.APPROVED, Decision.REJECTED):
            with self.subTest(decision=value), self.assertRaises(AuthorizationDenied):
                record_decision(
                    store,
                    same_identity,
                    actor(subject=same_identity.owner_id),
                    command(decision=value),
                    now=NOW,
                )
        self.assertEqual(store.decisions, {})

    def test_duplicate_decision_is_idempotent_and_conflicting_decision_loses(self):
        approved = record_decision(self.store, self.proposal, actor(), command(), now=NOW)
        duplicate = record_decision(
            self.store, self.proposal, actor(), command(), now=NOW + timedelta(seconds=1)
        )
        self.assertEqual(duplicate, approved)
        with self.assertRaises(Conflict):
            record_decision(
                self.store,
                self.proposal,
                actor(),
                command(decision=Decision.REJECTED),
                now=NOW + timedelta(seconds=2),
            )

    def test_concurrent_conflicting_decisions_commit_one_outcome(self):
        barrier = threading.Barrier(2)

        def decide(value):
            barrier.wait(timeout=5)
            try:
                return record_decision(
                    self.store,
                    self.proposal,
                    actor(),
                    command(decision=value),
                    now=NOW,
                )
            except Conflict as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, (Decision.APPROVED, Decision.REJECTED)))
        self.assertEqual(sum(isinstance(item, DecisionRecord) for item in results), 1)
        self.assertEqual(sum(isinstance(item, Conflict) for item in results), 1)

    def test_restart_reuses_original_durable_decision(self):
        original = record_decision(self.store, self.proposal, actor(), command(), now=NOW)
        restarted_store = self.store
        duplicate = record_decision(
            restarted_store,
            restarted_store.get_current_proposal(CASE_ID),
            actor(),
            command(),
            now=NOW + timedelta(seconds=5),
        )
        self.assertEqual(duplicate, original)
        self.assertEqual(len(restarted_store.decisions), 1)

    def test_changed_current_proposal_invalidates_prior_decision_command(self):
        self.store.current = proposal(proposal_version=2)
        with self.assertRaises(Conflict) as stale:
            record_decision(self.store, self.proposal, actor(), command(), now=NOW)
        self.assertEqual(stale.exception.code, "proposal_not_current")


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.proposal = proposal()
        self.store = MemoryStore(self.proposal)
        self.decision = record_decision(self.store, self.proposal, actor(), command(), now=NOW)
        self.destination = SyntheticIdempotentDestination()

    def coordinator(self):
        return EffectCoordinator(self.store, self.destination, deadline_seconds=1.0)

    def test_effect_identity_binds_case_version_action_and_destination(self):
        request = EffectRequest.create(self.proposal, {"amount": "18.50"})
        for changed in (
            replace(self.proposal, case_id=OTHER_CASE_ID),
            replace(self.proposal, proposal_version=2),
            replace(self.proposal, action="replacement_shipment"),
            replace(self.proposal, destination_id="shipping-api"),
        ):
            self.assertNotEqual(request.key, EffectRequest.create(changed, {"amount": "18.50"}).key)

    def test_timeout_after_send_is_unknown_then_restart_reconciles_without_resend(self):
        self.destination.timeout_after_send_once = True
        with self.assertRaises(OutcomeUnknown):
            self.coordinator().apply(
                self.proposal,
                self.store.current,
                self.decision,
                {"amount": "18.50"},
            )
        self.assertEqual(self.destination.effect_count(), 1)
        self.assertEqual(next(iter(self.store.effects.values())).status, EffectStatus.UNKNOWN)

        restarted = EffectCoordinator(self.store, self.destination, deadline_seconds=1.0)
        restarted.apply(
            self.proposal,
            self.store.current,
            self.decision,
            {"amount": "18.50"},
        )
        self.assertEqual(self.destination.effect_count(), 1)
        self.assertEqual(next(iter(self.store.effects.values())).status, EffectStatus.VERIFIED)

    def test_unknown_observation_blocks_retry(self):
        self.destination.force_unknown = True
        with self.assertRaises(OutcomeUnknown):
            self.coordinator().apply(
                self.proposal,
                self.store.current,
                self.decision,
                {"amount": "18.50"},
            )
        self.assertEqual(self.destination.effect_count(), 0)
        self.assertEqual(next(iter(self.store.effects.values())).status, EffectStatus.UNKNOWN)

    def test_duplicate_and_concurrent_retries_apply_one_synthetic_effect(self):
        def apply():
            return self.coordinator().apply(
                self.proposal,
                self.store.current,
                self.decision,
                {"amount": "18.50"},
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            requests = list(pool.map(lambda _: apply(), range(8)))
        self.assertEqual(self.destination.effect_count(), 1)
        self.assertEqual(len({request.key for request in requests}), 1)
        self.assertEqual(next(iter(self.store.effects.values())).status, EffectStatus.VERIFIED)

    def test_conflicting_effect_body_fails_closed(self):
        self.coordinator().apply(
            self.proposal,
            self.store.current,
            self.decision,
            {"amount": "18.50"},
        )
        with self.assertRaises(Conflict):
            self.coordinator().apply(
                self.proposal,
                self.store.current,
                self.decision,
                {"amount": "19.00"},
            )
        self.assertEqual(self.destination.effect_count(), 1)

    def test_rejection_and_stale_proposal_never_send(self):
        rejected = replace(self.decision, decision=Decision.REJECTED)
        with self.assertRaises(AuthorizationDenied):
            self.coordinator().apply(
                self.proposal,
                self.store.current,
                rejected,
                {"amount": "18.50"},
            )
        with self.assertRaises(Conflict):
            self.coordinator().apply(
                self.proposal,
                replace(self.proposal, proposal_version=2),
                self.decision,
                {"amount": "18.50"},
            )
        self.assertEqual(self.destination.effect_count(), 0)

    def test_stored_self_approval_never_authorizes_an_effect(self):
        same_identity = replace(self.proposal, reviewer_id=self.proposal.owner_id)
        decision = replace(self.decision, actor_id=same_identity.owner_id)
        with self.assertRaises(AuthorizationDenied):
            self.coordinator().apply(same_identity, same_identity, decision, {"amount": "18.50"})
        self.assertEqual(self.store.effects, {})
        self.assertEqual(self.destination.effect_count(), 0)

    def test_downstream_calls_share_one_bounded_deadline(self):
        self.coordinator().apply(
            self.proposal,
            self.store.current,
            self.decision,
            {"amount": "18.50"},
        )
        self.assertEqual(len(self.destination.timeouts), 3)
        self.assertTrue(all(0 < value <= 1.0 for value in self.destination.timeouts))
        self.assertGreaterEqual(self.destination.timeouts[0], self.destination.timeouts[-1])


if __name__ == "__main__":
    unittest.main()
