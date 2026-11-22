import hashlib
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.models import Case, Principal
from app.domain.policy import CaseAccessPolicy
from app.order_resolution.durability import Proposal
from app.order_resolution.workflow import OrderResolutionDecision
from order_resolution_hosted.application import (
    CallerContext,
    GeneratedOrderResolutionApplication,
)


class FakeStore:
    def __init__(self, case, proposal):
        self.case = case
        self.proposal = proposal
        self.decisions = []

    def get(self, case_id):
        if case_id != self.case.id:
            raise KeyError(case_id)
        return self.case

    def bind_decision_handle(self, case_id, handle, *, channel):
        self.proposal = replace(
            self.proposal,
            decision_handle_digest=hashlib.sha256(handle.encode()).hexdigest(),
            decision_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            decision_channel=channel,
        )
        return self.proposal

    def get_current_proposal(self, case_id):
        if case_id != self.proposal.case_id:
            raise KeyError(case_id)
        return self.proposal

    def claim_decision(self, decision):
        self.decisions.append(decision)
        return decision


class FakeBindings:
    def __init__(self, principal):
        self.principal = principal
        self.started = []
        self.resumed = []

    def resolve_principal(self, caller):
        return self.principal

    def bind_start(self, **binding):
        self.started.append(binding)

    def authorize_resume(self, **binding):
        self.resumed.append(binding)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.case_id = uuid4()
        self.case = Case(
            id=self.case_id,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload={"proposal": {"approval_required": True}},
            status="created",
            decision=None,
            request_id=None,
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=False,
            failure_code=None,
        )
        self.proposal = Proposal(
            case_id=str(self.case_id),
            proposal_version=1,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            input_digest="a" * 64,
            policy_evidence_digest="b" * 64,
            policy_version="v1",
            action="partial_refund_10",
            destination_id="synthetic-refund",
            approval_required=True,
            reason_codes=("manual_review",),
            decision_handle_digest=None,
            decision_expires_at=None,
            decision_channel=None,
        )
        self.principal = Principal(
            "tenant",
            "reviewer",
            frozenset({"workflow.read", "workflow.approve"}),
            frozenset({"Workflow.Approver"}),
        )
        self.store = FakeStore(self.case, self.proposal)
        self.bindings = FakeBindings(self.principal)
        self.application = GeneratedOrderResolutionApplication(
            store=self.store,
            action=object(),
            policy=CaseAccessPolicy(),
            identity_bindings=self.bindings,
            workflow_factory=lambda *_args: object(),
        )
        self.caller = CallerContext("opaque-user", "session-1", "call-1")

    def decision(self, **changes):
        value = {
            "case_id": self.case_id,
            "proposal_version": 1,
            "action": "partial_refund_10",
            "destination_id": "synthetic-refund",
            "handle": "request-1",
            "channel": "foundry-responses",
            "decision": "approved",
            "conversation_id": "conversation-1",
            "session_id": "session-1",
        }
        value.update(changes)
        return OrderResolutionDecision.model_validate(value)

    def test_authorizes_start_and_binds_opaque_caller_context(self):
        value = self.application.authorize_start(
            self.caller,
            "conversation-1",
            self.case_id,
        )
        self.assertEqual(value, {"case_id": str(self.case_id)})
        self.assertEqual(self.bindings.started[0]["caller"], self.caller)

    def test_structured_resume_records_authoritative_decision(self):
        response = self.application.authorize_resume(
            self.caller,
            "conversation-1",
            "request-1",
            self.decision(),
        )
        self.assertTrue(response.approved)
        self.assertEqual(self.store.decisions[0].actor_id, "reviewer")
        self.assertEqual(self.store.decisions[0].channel, "foundry-responses")
        self.assertEqual(self.bindings.resumed[0]["conversation_id"], "conversation-1")

    def test_rejects_cross_channel_and_cross_conversation_resume(self):
        for response, conversation in (
            (self.decision(channel="api"), "conversation-1"),
            (self.decision(conversation_id="other"), "conversation-1"),
            (self.decision(session_id="other"), "conversation-1"),
        ):
            with self.subTest(response=response):
                with self.assertRaises(PermissionError):
                    self.application.authorize_resume(
                        self.caller,
                        conversation,
                        "request-1",
                        response,
                    )


if __name__ == "__main__":
    unittest.main()
