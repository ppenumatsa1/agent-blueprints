import asyncio
import unittest
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from app.api.schemas import case_output
from app.api.routes.cases import decide, read, submit
from app.api.schemas import DecisionInput, Submission
from app.domain.models import Case
from app.order_resolution.service import OrderResolutionService


class CaseOutputChannelTests(unittest.TestCase):
    def test_channel_matches_host_and_is_only_exposed_with_pending_handle(self):
        case = Case(
            id=UUID("80000000-0000-4000-8000-000000000008"),
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload={},
            status="pending",
            decision=None,
            request_id="opaque",
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=False,
            failure_code=None,
        )
        self.assertEqual(case_output(case).decision_channel, "api")
        self.assertEqual(case_output(case, hosted_mode=True).decision_channel, "foundry-responses")
        for unavailable in (replace(case, request_id=None), replace(case, status="created")):
            output = case_output(unavailable, hosted_mode=True)
            self.assertIsNone(output.decision_handle)
            self.assertIsNone(output.decision_channel)

    def test_routes_publish_selected_host_channel(self):
        case = Case(
            id=UUID("80000000-0000-4000-8000-000000000008"),
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload={},
            status="pending",
            decision=None,
            request_id="opaque",
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=False,
            failure_code=None,
        )
        service = Mock(spec=OrderResolutionService)
        service.submit = AsyncMock(return_value=case)
        service.decide_bound = AsyncMock(return_value=case)
        service.read.return_value = case
        service.store = Mock()
        actor = SimpleNamespace(principal=object())

        async def exercise(hosted):
            service.hosted_mode = hosted
            submitted = await submit(
                Submission(reviewer_id=case.id, payload={}), actor, service, "key"
            )
            decided = await decide(case.id, DecisionInput(decision="approved"), actor, service)
            return submitted, decided

        for hosted, channel in ((False, "api"), (True, "foundry-responses")):
            for output in asyncio.run(exercise(hosted)):
                self.assertEqual(output.decision_channel, channel)
            with patch("app.api.routes.cases.poll_read", return_value=nullcontext()):
                self.assertEqual(read(case.id, actor, service).decision_channel, channel)
