import asyncio
import hashlib
import io
import time
from email.message import Message
import urllib.error
import urllib.request
import unittest
from copy import deepcopy
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import current_identity, workflow_service
from app.api.routes.acceptance import _authorized, case_control
from app.api.routes.cases import router as cases_router
from app.config import Settings
from app.domain.errors import AccessDenied, NotFound
from app.domain.models import Case, Principal
from app.infrastructure.identity import AuthenticatedRequest
from app.order_resolution.acceptance import AcceptanceFaults
from app.order_resolution.durability import Decision, Proposal
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.service import OrderResolutionService
from tests.hosted_failure_runner import (
    ReconciliationRequired,
    UnsupportedScenario,
    _load_adapter,
)
from tests.live_acceptance import (
    FoundryModelEvaluator,
    LiveClient,
    LiveHostedFailureAdapter,
    create_results,
    _https_origin,
    _RejectRedirects,
)


CASE_ID = UUID("10000000-0000-4000-8000-000000000001")
REVISION = "a" * 40


class FakeResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class FakeConnection:
    def __init__(self):
        self.results = [
            {
                "approved": 0,
                "rejected": 0,
                "approval_requests": 0,
                "claims": 1,
                "effects": 1,
                "terminal": 1,
                "denials": 0,
            },
            [{"action": "partial_refund_10", "amount": "7.90", "currency": "USD"}],
        ]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args):
        return FakeResult(self.results.pop(0))


class AcceptanceFaultTests(unittest.TestCase):
    def test_poc_owner_grant_uses_pending_case_and_exact_handle_digest(self):
        client = object.__new__(LiveClient)
        client.poc_owner_database_url = "synthetic-poc-owner-url"
        case = {
            "id": str(CASE_ID),
            "status": "pending",
            "decision_handle": "test-native-request",
            "payload": {
                "proposal": {
                    "version": 1,
                    "action": "replacement_shipment",
                    "destination_id": "synthetic-fulfillment",
                }
            },
        }
        with patch("app.order_resolution.poc_grant.issue_grant") as issue_grant:
            with self.assertRaises(ValueError):
                client.grant_poc_decision({**case, "status": "created"}, "rejected")
            issue_grant.assert_not_called()
            client.grant_poc_decision(case, "rejected")
        issue_grant.assert_called_once_with(
            "synthetic-poc-owner-url",
            case_id=CASE_ID,
            proposal_version=1,
            handle_digest=hashlib.sha256(b"test-native-request").hexdigest(),
            action="replacement_shipment",
            destination_id="synthetic-fulfillment",
            decision=Decision.REJECTED,
        )

    def test_single_identity_is_accepted_only_in_explicit_poc_mode(self):
        actor = {"object_id": str(uuid4()), "claims": {"tid": str(uuid4())}}
        with (
            patch.dict("os.environ", {"MAF_LIVE_AUTHORIZED_ORIGIN": "https://example.invalid"}),
            patch("tests.live_acceptance._read_auth"),
            patch("tests.live_acceptance._identity", return_value=actor) as identity,
        ):
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                LiveClient("https://example.invalid", "unused", REVISION)
            client = LiveClient(
                "https://example.invalid",
                "unused",
                REVISION,
                poc_owner_database_url="synthetic-poc-owner-url",
            )
            self.assertEqual(client.owner, actor)
            identity.side_effect = [actor, actor, {**actor, "object_id": str(uuid4())}]
            with self.assertRaisesRegex(ValueError, "one exact owner/reviewer/operator"):
                LiveClient(
                    "https://example.invalid",
                    "unused",
                    REVISION,
                    poc_owner_database_url="synthetic-poc-owner-url",
                )

    def test_live_submission_body_passes_generated_api_schema(self):
        owner_id = str(uuid4())
        reviewer_id = str(uuid4())
        principal = object()
        identity = SimpleNamespace(principal=principal)
        payload = {"order": {"id": "synthetic-order"}}
        service = SimpleNamespace(
            submit=AsyncMock(
                return_value=SimpleNamespace(
                    id=CASE_ID,
                    status="completed",
                    decision=None,
                    payload=payload,
                    execution_complete=True,
                    failure_code=None,
                )
            )
        )
        app = FastAPI()
        app.include_router(cases_router, prefix="/api")
        app.dependency_overrides[current_identity] = lambda: identity
        app.dependency_overrides[workflow_service] = lambda: service
        client = object.__new__(LiveClient)
        client.base_url = "https://example.invalid"
        client.owner = {"object_id": owner_id, "access_token": "synthetic"}
        client.correlations = []
        request_bodies = []

        with TestClient(app) as api:

            def open_request(request, timeout):
                request_bodies.append(request.data)
                response = api.request(
                    request.method,
                    request.full_url,
                    content=request.data,
                    headers=dict(request.header_items()),
                )
                return SimpleNamespace(
                    status=response.status_code,
                    headers=response.headers,
                    read=lambda: response.content,
                )

            client.opener = SimpleNamespace(open=open_request)
            for mode, poc_url, assigned, explicit, expected in (
                ("poc-unassigned", "synthetic-poc-url", owner_id, None, None),
                ("poc-explicit", "synthetic-poc-url", owner_id, owner_id, owner_id),
                ("ordinary", None, reviewer_id, None, reviewer_id),
            ):
                with self.subTest(mode=mode):
                    service.submit.reset_mock()
                    client.poc_owner_database_url = poc_url
                    client.reviewer = {"object_id": assigned}
                    client.submit(payload, "synthetic-key", reviewer_id=explicit)
                    service.submit.assert_awaited_once()
                    actual_principal, actual_reviewer, actual_payload, actual_key = (
                        service.submit.await_args.args
                    )
                    self.assertIs(actual_principal, principal)
                    self.assertEqual(actual_payload, payload)
                    self.assertEqual(actual_key, "synthetic-key")
                    if expected is None:
                        self.assertNotEqual(UUID(actual_reviewer), UUID(owner_id))
                        first_body = request_bodies[-1]
                        client.submit(payload, "synthetic-key")
                        self.assertEqual(request_bodies[-1], first_body)
                        self.assertEqual(service.submit.await_args.args[1], actual_reviewer)
                    else:
                        self.assertEqual(UUID(actual_reviewer), UUID(expected))

    def test_poc_unassigned_reviewer_cannot_equal_operator(self):
        client = object.__new__(LiveClient)
        client.owner = {"object_id": str(UUID(int=0))}
        client.reviewer = client.owner
        client.poc_owner_database_url = "synthetic-poc-url"
        client.request = Mock(return_value=(200, {}, {}))
        with self.assertRaisesRegex(ValueError, "unassigned reviewer"):
            client.submit({}, "synthetic-key")
        client.request.assert_not_called()

    def test_selected_poc_decisions_grant_before_resuming_as_same_actor(self):
        actor = {"object_id": str(uuid4())}
        client = Mock(owner=actor, reviewer=actor)
        pending = {"id": str(CASE_ID), "status": "pending"}
        client.submit.return_value = (pending, {})
        client.wait_for_pending.return_value = pending
        completed = {"id": str(CASE_ID), "status": "completed"}
        client.decide.return_value = (200, completed, {})
        client.wait_for_completion.return_value = completed
        client.snapshot.return_value = {"status": "completed", "counts": {"rejected": 1}}
        with (
            patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "synthetic-poc-url"}),
            patch("tests.live_acceptance.LiveClient", return_value=client) as factory,
            patch(
                "tests.live_acceptance._result",
                return_value={
                    "business_outcome": {},
                    "technical_execution": {"authorized_decision_count": 1},
                },
            ),
        ):
            results = create_results(
                base_url="https://example.invalid",
                auth_file="unused",
                source_revision=REVISION,
                deployment_revision=REVISION,
                case_ids=["ORS-002", "ORS-003"],
            )
        factory.assert_called_once_with(
            "https://example.invalid",
            "unused",
            REVISION,
            poc_owner_database_url="synthetic-poc-url",
        )
        self.assertTrue(
            all(
                call.kwargs == {"reviewer_id": actor["object_id"]}
                for call in client.submit.call_args_list
            )
        )
        self.assertEqual(
            [
                (call[0], call.args)
                for call in client.mock_calls
                if call[0] in ("grant_poc_decision", "decide")
            ],
            [
                ("grant_poc_decision", (pending, "approved")),
                ("decide", (pending, "approved", actor)),
                ("grant_poc_decision", (pending, "rejected")),
                ("decide", (pending, "rejected", actor)),
            ],
        )
        self.assertEqual(results["ORS-005"]["status"], "not_run")
        self.assertEqual(results["ORS-009"]["status"], "not_run")

    def test_model_endpoint_requires_separately_authorized_https_origin(self):
        auth = {
            "model": {
                "endpoint": "https://model.example.test/v1?api-version=1",
                "access_token": "synthetic",
            }
        }
        with (
            patch.dict("os.environ", {"MAF_MODEL_AUTHORIZED_ORIGIN": ""}),
            patch("tests.live_acceptance._read_auth") as read_auth,
            self.assertRaises(ValueError),
        ):
            FoundryModelEvaluator(provider_id="test", model_id="test", auth_file="unused")
        read_auth.assert_not_called()
        for endpoint in (
            "http://model.example.test/v1",
            "https://attacker.example/v1",
            "https://model.example.test@attacker.example/v1",
            "https://model.example.test\\@attacker.example/v1",
            "https://model.example.test/v1#fragment",
        ):
            auth["model"]["endpoint"] = endpoint
            with (
                self.subTest(endpoint=endpoint),
                patch.dict(
                    "os.environ",
                    {"MAF_MODEL_AUTHORIZED_ORIGIN": "https://model.example.test"},
                ),
                patch("tests.live_acceptance._read_auth", return_value=auth),
                self.assertRaises(ValueError),
            ):
                FoundryModelEvaluator(provider_id="test", model_id="test", auth_file="unused")

    def test_model_evaluator_rejects_redirect_without_forwarding_bearer(self):
        observed = []

        class FakeHTTPS(urllib.request.BaseHandler):
            handler_order = 100

            def https_open(self, request):
                observed.append((request.full_url, request.get_header("Authorization")))
                headers = Message()
                headers["Location"] = "https://attacker.example/steal"
                response = urllib.response.addinfourl(
                    io.BytesIO(b""), headers, request.full_url, 302
                )
                response.msg = "Found"
                return response

        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _RejectRedirects(), FakeHTTPS()
        )
        auth = {
            "model": {
                "endpoint": "https://model.example.test/v1?api-version=1",
                "access_token": "synthetic-canary",
            }
        }
        with (
            patch.dict(
                "os.environ",
                {"MAF_MODEL_AUTHORIZED_ORIGIN": "https://model.example.test"},
            ),
            patch("tests.live_acceptance._read_auth", return_value=auth),
            patch("tests.live_acceptance.urllib.request.build_opener", return_value=opener),
        ):
            evaluator = FoundryModelEvaluator(
                provider_id="test", model_id="test", auth_file="unused"
            )
            item = SimpleNamespace(
                query="synthetic", response="synthetic", expected_output="synthetic"
            )
            with self.assertRaisesRegex(RuntimeError, "redirects are not permitted"):
                asyncio.run(evaluator.evaluate([item], eval_name="test"))
        self.assertEqual(
            observed,
            [
                (
                    "https://model.example.test/v1?api-version=1",
                    "Bearer synthetic-canary",
                )
            ],
        )

    def test_live_hosted_interruption_cannot_stop_a_session_without_verified_continuation(
        self,
    ):
        adapter = object.__new__(LiveHostedFailureAdapter)
        adapter.client = Mock()
        with (
            patch.dict(
                "os.environ",
                {"HOSTED_ROOT": "synthetic-root", "AZURE_ENV_NAME": "test"},
            ),
            patch("tests.live_acceptance.subprocess.run") as run,
            self.assertRaises(UnsupportedScenario),
        ):
            adapter.interrupt_host("synthetic-case")
        run.assert_not_called()
        self.assertEqual(adapter.client.mock_calls, [])

    def test_unverified_reconciliation_preserves_unknown_and_interrupted_state(self):
        adapter = object.__new__(LiveHostedFailureAdapter)
        adapter.interrupted = {"synthetic-case"}
        adapter.unknown = {"synthetic-case"}
        adapter.read = Mock()
        with self.assertRaises(UnsupportedScenario):
            adapter.reconcile("synthetic-case")
        self.assertEqual(adapter.interrupted, {"synthetic-case"})
        self.assertEqual(adapter.unknown, {"synthetic-case"})
        adapter.read.assert_not_called()
        with self.assertRaises(ReconciliationRequired):
            adapter.retry("synthetic-case")

    def test_live_origin_must_be_https_and_explicitly_authorized_before_auth_is_read(
        self,
    ):
        invalid = (
            "",
            "http://api.example.test",
            "https://api.example.test/path",
            "https://api.example.test?query",
            "https://api.example.test#fragment",
            "https://api.example.test@attacker.example",
            "https://api.example.test\\@attacker.example",
            "https://api.example.test:",
            "https://api.example.test:0",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                _https_origin(value)
        self.assertEqual(_https_origin("HTTPS://API.EXAMPLE.TEST:443/"), "https://api.example.test")
        with (
            patch.dict("os.environ", {"MAF_LIVE_AUTHORIZED_ORIGIN": "https://api.example.test"}),
            patch("tests.live_acceptance._read_auth") as read_auth,
            self.assertRaises(ValueError),
        ):
            LiveClient("https://attacker.example", "unused", REVISION)
        read_auth.assert_not_called()
        with (
            patch.dict("os.environ", {"MAF_LIVE_AUTHORIZED_ORIGIN": ""}),
            patch("tests.live_acceptance._read_auth") as read_auth,
            self.assertRaises(ValueError),
        ):
            LiveClient("https://api.example.test", "unused", REVISION)
        read_auth.assert_not_called()

    def test_live_client_rejects_redirect_before_sending_bearer_to_other_origin(self):
        observed = []
        location = ""

        class FakeHTTPS(urllib.request.BaseHandler):
            handler_order = 100

            def https_open(self, request):
                observed.append((request.full_url, request.get_header("Authorization")))
                headers = Message()
                headers["Location"] = location
                response = urllib.response.addinfourl(
                    io.BytesIO(b""), headers, request.full_url, 302
                )
                response.msg = "Found"
                return response

        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _RejectRedirects(), FakeHTTPS()
        )
        client.deployment_revision = REVISION
        client.correlations = []
        for location in (
            "https://attacker.example/steal",
            "http://api.example.test/steal",
            "https://api.example.test/other",
        ):
            with self.subTest(location=location):
                observed.clear()
                with self.assertRaisesRegex(RuntimeError, "redirects are not permitted"):
                    client.request("GET", "/api/cases", {"access_token": "synthetic-canary"})
                self.assertEqual(
                    observed,
                    [("https://api.example.test/api/cases", "Bearer synthetic-canary")],
                )

    def test_live_client_rejects_non_origin_relative_request_paths(self):
        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.opener = Mock()
        for path in (
            "//attacker.example",
            "https://attacker.example",
            "/\\attacker",
            "/x\nHeader: x",
            "/x#fragment",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                client.request("GET", path, {"access_token": "synthetic-canary"})
        client.opener.open.assert_not_called()

    def test_failure_adapter_uses_runner_target_and_failure_auth(self):
        environment = {
            "SOURCE_REVISION": REVISION,
            "DEPLOYMENT_REVISION": REVISION,
            "AGENT_VERSION": "1",
            "MAF_HOSTED_FAILURE_AUTH_FILE": "synthetic-auth.json",
        }
        with (
            patch.dict("os.environ", environment, clear=True),
            patch("tests.live_acceptance.LiveClient") as client,
        ):
            adapter = _load_adapter(
                "tests.live_acceptance:create_failure_adapter",
                "https://example.invalid",
                "synthetic-nonproduction",
                "synthetic-target",
            )
        client.assert_called_once_with("https://example.invalid", "synthetic-auth.json", REVISION)
        self.assertEqual(adapter.target_kind, "synthetic-nonproduction")
        self.assertEqual(adapter.target_id, "synthetic-target")

    def test_failure_adapter_waits_for_hosted_pending_and_completion(self):
        case_id = str(CASE_ID)
        handle = "20000000-0000-4000-8000-000000000002"
        created = {"id": case_id, "status": "created", "decision_handle": None}
        pending = {
            "id": case_id,
            "status": "pending",
            "decision_handle": handle,
            "decision_channel": "foundry-responses",
            "payload": {"proposal": {}},
        }
        completed = {
            **pending,
            "status": "completed",
            "execution_complete": True,
            "decision_handle": None,
        }
        client = object.__new__(LiveClient)
        client.owner = {"object_id": "owner"}
        client.reviewer = {"object_id": "reviewer"}
        client.submit = Mock(return_value=(created, {}))
        client._read_for_poll = AsyncMock(side_effect=[pending, completed])
        client.decide = Mock(return_value=(200, pending, {}))
        client.snapshot = Mock(
            side_effect=[
                {"status": "pending", "counts": {"effects": 0}},
                {"status": "completed", "counts": {"effects": 1}},
            ]
        )
        adapter = object.__new__(LiveHostedFailureAdapter)
        adapter.client = client
        adapter.records = {}
        adapter.keys = {}
        adapter.interrupted = set()
        adapter.unknown = set()
        adapter.timeout_after_effect = False

        with patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0):
            initial = adapter.create("synthetic-key")
            final = adapter.approve(case_id, request_id=handle)

        self.assertEqual((initial.business_outcome, initial.effect_count), ("pending", 0))
        self.assertEqual((final.business_outcome, final.effect_count), ("completed", 1))
        self.assertEqual(client._read_for_poll.await_count, 2)
        client.decide.assert_called_once()

    def test_failure_adapter_does_not_invent_a_missing_pending_handle(self):
        client = object.__new__(LiveClient)
        client.submit = Mock(
            return_value=(
                {"id": str(CASE_ID), "status": "created", "decision_handle": None},
                {},
            )
        )
        client._read_for_poll = AsyncMock(
            return_value={
                "id": str(CASE_ID),
                "status": "failed",
                "failure_code": "hosted_failure",
            }
        )
        adapter = object.__new__(LiveHostedFailureAdapter)
        adapter.client = client
        adapter.records = {}
        adapter.keys = {}
        with (
            patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0),
            self.assertRaises(RuntimeError),
        ):
            adapter.create("synthetic-key")
        client._read_for_poll.assert_awaited_once_with(str(CASE_ID))
        self.assertFalse(adapter.records)

    def test_provider_results_do_not_infer_native_continuation_from_completion(self):
        client = Mock()
        with (
            patch(
                "tests.live_acceptance.GOLDEN_CASES",
                [{"id": "ORS-001"}, {"id": "ORS-005"}],
            ),
            patch("tests.live_acceptance.LiveClient", return_value=client),
            self.assertRaisesRegex(UnsupportedScenario, "native continuation"),
        ):
            create_results(
                base_url="https://example.invalid",
                auth_file="unused",
                source_revision=REVISION,
                deployment_revision=REVISION,
            )
        client.submit.assert_not_called()
        client.decide.assert_not_called()

    def test_explicit_subset_runs_selected_case_and_records_omissions_as_not_run(self):
        client = Mock()
        record = {"id": str(CASE_ID), "status": "completed"}
        client.submit.return_value = (record, {})
        client.wait_for_completion.return_value = record
        snapshot = {"status": "completed"}
        with (
            patch(
                "tests.live_acceptance.GOLDEN_CASES",
                [{"id": "ORS-001"}, {"id": "ORS-005"}, {"id": "ORS-009"}],
            ),
            patch("tests.live_acceptance.LiveClient", return_value=client),
            patch("tests.live_acceptance._payload", return_value={}),
            patch("tests.live_acceptance._result", return_value={"observed": True}) as result,
        ):
            client.snapshot.return_value = snapshot
            results = create_results(
                base_url="https://example.invalid",
                auth_file="unused",
                source_revision=REVISION,
                deployment_revision=REVISION,
                case_ids=["ORS-001"],
            )
        self.assertEqual(results["ORS-001"], {"observed": True})
        for case_id in ("ORS-005", "ORS-009"):
            self.assertEqual(results[case_id]["status"], "not_run")
            self.assertNotIn("business_outcome", results[case_id])
        client.submit.assert_called_once()
        result.assert_called_once_with(snapshot, native_pause=False, extras={})

    def test_ors004_replays_before_completion_and_compares_terminal_outcome(self):
        created = {
            "id": str(CASE_ID),
            "status": "created",
            "execution_complete": False,
            "decision": "pending",
            "payload": {"proposal": {"amount": "7.90"}},
            "failure_code": None,
        }
        completed = {**created, "status": "completed", "execution_complete": True}
        snapshot = {
            "status": "completed",
            "execution_complete": True,
            "failure_code": None,
            "decision": None,
            "proposal": {
                "action": "partial_refund_10",
                "amount": "7.90",
                "currency": "USD",
                "approval_required": False,
            },
            "verified_actions": [
                {"type": "partial_refund_10", "amount": "7.90", "currency": "USD"}
            ],
            "counts": {"approved": 0, "claims": 1, "effects": 1, "terminal": 1},
        }
        for mismatch in ("none", "record", "snapshot"):
            with self.subTest(mismatch=mismatch):
                client = Mock(owner={"object_id": str(uuid4())})
                replay = deepcopy(completed)
                after = deepcopy(snapshot)
                if mismatch == "record":
                    replay["payload"]["proposal"]["amount"] = "8.00"
                elif mismatch == "snapshot":
                    after["verified_actions"][0]["amount"] = "8.00"
                client.submit.side_effect = [(created, {}), (created, {}), (replay, {})]
                client.wait_for_completion.return_value = completed
                client.snapshot.side_effect = [snapshot, after]
                with (
                    patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "synthetic"}),
                    patch("tests.live_acceptance.LiveClient", return_value=client),
                ):
                    results = create_results(
                        base_url="https://example.invalid",
                        auth_file="unused",
                        source_revision=REVISION,
                        deployment_revision=REVISION,
                        case_ids=["ORS-004"],
                    )
                calls = [
                    call[0]
                    for call in client.mock_calls
                    if call[0] in ("submit", "wait_for_completion", "snapshot")
                ]
                self.assertEqual(
                    calls,
                    [
                        "submit",
                        "submit",
                        "wait_for_completion",
                        "snapshot",
                        "submit",
                        "snapshot",
                    ],
                )
                first, before, after_call = client.submit.call_args_list
                self.assertEqual(first, before)
                self.assertEqual(first, after_call)
                self.assertTrue(
                    results["ORS-004"]["technical_execution"]["request_identity_reused"]
                )
                self.assertEqual(
                    results["ORS-004"]["business_outcome"]["returned_original_outcome"],
                    mismatch == "none",
                )

    def test_ors004_marks_unobserved_precompletion_replay_unverified(self):
        created = {"id": str(CASE_ID), "status": "created", "execution_complete": False}
        completed = {
            "id": str(CASE_ID),
            "status": "completed",
            "execution_complete": True,
        }
        for first, replay in ((completed, completed), (created, completed)):
            with self.subTest(first=first["status"]):
                client = Mock(owner={"object_id": str(uuid4())})
                client.submit.side_effect = [(first, {}), (replay, {})]
                client.wait_for_completion.return_value = completed
                client.snapshot.return_value = {
                    "status": "completed",
                    "proposal": None,
                    "decision": None,
                    "verified_actions": [],
                    "counts": {"approved": 0, "claims": 0, "effects": 0, "terminal": 1},
                }
                with (
                    patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "synthetic"}),
                    patch("tests.live_acceptance.LiveClient", return_value=client),
                ):
                    results = create_results(
                        base_url="https://example.invalid",
                        auth_file="unused",
                        source_revision=REVISION,
                        deployment_revision=REVISION,
                        case_ids=["ORS-004"],
                    )
                self.assertEqual(results["ORS-004"]["status"], "unverified")
                self.assertNotIn("business_outcome", results["ORS-004"])
                client.wait_for_completion.assert_not_called()

    def test_ors004_rejects_a_different_case_on_either_replay(self):
        created = {"id": str(CASE_ID), "status": "created", "execution_complete": False}
        completed = {
            **created,
            "status": "completed",
            "execution_complete": True,
            "decision": "pending",
            "payload": {"proposal": None},
            "failure_code": None,
        }
        snapshot = {
            "status": "completed",
            "execution_complete": True,
            "failure_code": None,
            "decision": None,
            "proposal": None,
            "verified_actions": [],
            "counts": {"approved": 0, "claims": 0, "effects": 0, "terminal": 1},
        }
        for mismatch in ("before", "after"):
            with self.subTest(mismatch=mismatch):
                client = Mock(owner={"object_id": str(uuid4())})
                other = {**created, "id": str(uuid4())}
                client.submit.side_effect = [
                    (created, {}),
                    (other if mismatch == "before" else created, {}),
                    (other, {}),
                ]
                client.wait_for_completion.return_value = completed
                client.snapshot.return_value = snapshot
                with (
                    patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "synthetic"}),
                    patch("tests.live_acceptance.LiveClient", return_value=client),
                    self.assertRaisesRegex(RuntimeError, "ORS-004 .* different case"),
                ):
                    create_results(
                        base_url="https://example.invalid",
                        auth_file="unused",
                        source_revision=REVISION,
                        deployment_revision=REVISION,
                        case_ids=["ORS-004"],
                    )

    def test_ors004_rejects_missing_terminal_evidence(self):
        created = {"id": str(CASE_ID), "status": "created", "execution_complete": False}
        completed = {
            **created,
            "status": "completed",
            "execution_complete": True,
            "decision": "pending",
            "payload": {"proposal": None},
            "failure_code": None,
        }
        snapshot = {
            "status": "completed",
            "execution_complete": True,
            "decision": None,
            "proposal": None,
            "verified_actions": [],
            "counts": {"approved": 0, "claims": 0, "effects": 0, "terminal": 1},
        }
        client = Mock(owner={"object_id": str(uuid4())})
        client.submit.side_effect = [(created, {}), (created, {}), (completed, {})]
        client.wait_for_completion.return_value = completed
        client.snapshot.return_value = snapshot
        with (
            patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "synthetic"}),
            patch("tests.live_acceptance.LiveClient", return_value=client),
            self.assertRaisesRegex(RuntimeError, "ORS-004 terminal business evidence"),
        ):
            create_results(
                base_url="https://example.invalid",
                auth_file="unused",
                source_revision=REVISION,
                deployment_revision=REVISION,
                case_ids=["ORS-004"],
            )

    def test_ors008_requires_each_observed_failure_and_one_terminal_event(self):
        def fixtures():
            records = [
                {
                    "id": str(uuid4()),
                    "status": "failed",
                    "execution_complete": True,
                    "failure_code": "policy_evidence_invalid",
                    "decision": "pending",
                    "payload": {
                        "proposal": None,
                        "resolution_failure": "policy_evidence_invalid",
                    },
                }
                for _ in range(3)
            ]
            snapshots = [
                {
                    "status": "failed",
                    "execution_complete": True,
                    "failure_code": "policy_evidence_invalid",
                    "proposal": None,
                    "decision": None,
                    "verified_actions": [],
                    "counts": {
                        "approved": 0,
                        "rejected": 0,
                        "approval_requests": 0,
                        "claims": 0,
                        "effects": 0,
                        "terminal": 1,
                    },
                }
                for _ in records
            ]
            return records, snapshots

        def run(records, snapshots):
            client = Mock(owner={"object_id": str(uuid4())})
            client.submit.side_effect = [(record, {}) for record in records]
            client.snapshot.side_effect = snapshots
            with (
                patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "synthetic"}),
                patch("tests.live_acceptance.LiveClient", return_value=client),
            ):
                return create_results(
                    base_url="https://example.invalid",
                    auth_file="unused",
                    source_revision=REVISION,
                    deployment_revision=REVISION,
                    case_ids=["ORS-008"],
                )

        records, snapshots = fixtures()
        result = run(records, snapshots)["ORS-008"]
        self.assertEqual(result["business_outcome"]["error"], "policy_evidence_invalid")
        self.assertEqual(result["technical_execution"]["terminal_event_count_per_variant"], 1)
        self.assertTrue(result["technical_execution"]["all_variants_failed_explicitly"])

        for mismatch in (
            "record_error",
            "snapshot_error",
            "terminal",
            "payload_proposal",
            "payload_error",
            "proposal",
            "decision",
            "actions",
            "approval",
            "approved",
            "claim",
            "effect",
            "missing_count",
            "boolean_count",
        ):
            with self.subTest(mismatch=mismatch):
                records, snapshots = fixtures()
                if mismatch == "record_error":
                    records[1]["failure_code"] = "policy_evidence_missing"
                elif mismatch == "snapshot_error":
                    snapshots[1]["failure_code"] = "policy_evidence_missing"
                elif mismatch == "terminal":
                    snapshots[1]["counts"]["terminal"] = 2
                elif mismatch == "payload_proposal":
                    records[1]["payload"]["proposal"] = {"action": "replacement_shipment"}
                elif mismatch == "payload_error":
                    records[1]["payload"]["resolution_failure"] = "policy_evidence_missing"
                elif mismatch == "proposal":
                    snapshots[1]["proposal"] = {"action": "replacement_shipment"}
                elif mismatch == "decision":
                    snapshots[1]["decision"] = "approved"
                elif mismatch == "actions":
                    snapshots[1]["verified_actions"] = [{"type": "replacement_shipment"}]
                elif mismatch == "approval":
                    snapshots[1]["counts"]["approval_requests"] = 1
                elif mismatch == "approved":
                    snapshots[1]["counts"]["approved"] = 1
                elif mismatch == "claim":
                    snapshots[1]["counts"]["claims"] = 1
                elif mismatch == "effect":
                    snapshots[1]["counts"]["effects"] = 1
                elif mismatch == "missing_count":
                    del snapshots[1]["counts"]["approval_requests"]
                else:
                    snapshots[1]["counts"]["terminal"] = True
                with self.assertRaisesRegex(RuntimeError, "ORS-008"):
                    run(records, snapshots)

    def test_single_identity_no_decision_subset_never_grants_or_decides(self):
        actor_id = str(uuid4())
        client = object.__new__(LiveClient)
        client.owner = {"object_id": actor_id}
        client.reviewer = client.owner
        client.poc_owner_database_url = "synthetic-poc-url"
        client.grant_poc_decision = Mock(side_effect=AssertionError("unexpected grant"))
        client.decide = Mock(side_effect=AssertionError("unexpected decision"))
        client.wait_for_pending = Mock(side_effect=AssertionError("unexpected pending case"))
        submissions = []
        records = {}
        records_by_id = {}

        def finish(record, _status):
            stored = records_by_id[record["id"]]
            if stored["status"] == "created":
                stored.update(status="completed", execution_complete=True)
            return deepcopy(stored)

        client.wait_for_completion = Mock(side_effect=finish)

        def request(method, path, identity, *, body, idempotency_key, hosted_phase):
            self.assertEqual((method, path, hosted_phase), ("POST", "/api/cases", "start"))
            self.assertIs(identity, client.owner)
            self.assertNotEqual(UUID(body["reviewer_id"]), UUID(actor_id))
            submissions.append((idempotency_key, body))
            if idempotency_key not in records:
                failed = not idempotency_key.startswith("live-") or idempotency_key.startswith(
                    ("live-ors-006-", "live-ors-007-")
                )
                status = (
                    "failed"
                    if failed
                    else "created"
                    if idempotency_key.startswith("live-ors-004-")
                    else "completed"
                )
                failure_code = (
                    "policy_evidence_invalid"
                    if not idempotency_key.startswith("live-")
                    else "synthetic-failure"
                    if failed
                    else None
                )
                record = {
                    "id": str(uuid4()),
                    "status": status,
                    "execution_complete": status != "created",
                    "decision": "pending",
                    "failure_code": failure_code,
                    "payload": {
                        "proposal": None if failed else {"action": "partial_refund_10"},
                        **({"resolution_failure": failure_code} if failed else {}),
                    },
                }
                records[idempotency_key] = record
                records_by_id[record["id"]] = record
            return 200, deepcopy(records[idempotency_key]), {}

        def snapshot(case_id):
            record = records_by_id[case_id]
            return {
                "status": record["status"],
                "execution_complete": record["execution_complete"],
                "failure_code": record["failure_code"],
                "proposal": (
                    None
                    if record["status"] == "failed"
                    else {
                        "action": "partial_refund_10",
                        "amount": "7.90",
                        "currency": "USD",
                        "approval_required": False,
                    }
                ),
                "decision": None,
                "verified_actions": [],
                "counts": {
                    "approved": 0,
                    "rejected": 0,
                    "approval_requests": 0,
                    "claims": 0,
                    "effects": 0,
                    "terminal": 1,
                },
            }

        client.request = Mock(side_effect=request)
        client.snapshot = Mock(side_effect=snapshot)
        selected = ["ORS-001", "ORS-004", "ORS-006", "ORS-007", "ORS-008"]
        with (
            patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "synthetic-poc-url"}),
            patch("tests.live_acceptance.LiveClient", return_value=client),
        ):
            results = create_results(
                base_url="https://example.invalid",
                auth_file="unused",
                source_revision=REVISION,
                deployment_revision=REVISION,
                case_ids=selected,
            )

        for case_id in selected:
            self.assertIn("business_outcome", results[case_id])
        for case_id in ("ORS-002", "ORS-003", "ORS-005", "ORS-009"):
            self.assertEqual(results[case_id]["status"], "not_run")
            self.assertNotIn("business_outcome", results[case_id])
        client.grant_poc_decision.assert_not_called()
        client.decide.assert_not_called()
        client.wait_for_pending.assert_not_called()
        repeated = [item for item in submissions if item[0].startswith("live-ors-004-")]
        self.assertEqual(len(repeated), 3)
        self.assertTrue(all(item == repeated[0] for item in repeated))
        self.assertEqual(
            {body["reviewer_id"] for _, body in submissions}, {repeated[0][1]["reviewer_id"]}
        )
        self.assertTrue(results["ORS-004"]["technical_execution"]["request_identity_reused"])

    def test_invalid_or_blocked_subset_fails_before_constructing_live_client(self):
        selections = ([], ["ORS-010"], ["ORS-001", "ORS-001"], ["ORS-001", "ORS-005"])
        for selected in selections:
            with (
                self.subTest(selected=selected),
                patch("tests.live_acceptance.LiveClient") as client,
                self.assertRaises((ValueError, UnsupportedScenario)),
            ):
                create_results(
                    base_url="https://example.invalid",
                    auth_file="unused",
                    source_revision=REVISION,
                    deployment_revision=REVISION,
                    case_ids=selected,
                )
            client.assert_not_called()
        with (
            patch.dict("os.environ", {"MAF_LIVE_POC_OWNER_DATABASE_URL": "unused"}),
            patch("tests.live_acceptance.LiveClient") as client,
            self.assertRaisesRegex(UnsupportedScenario, "distinct actor identities"),
        ):
            create_results(
                base_url="https://example.invalid",
                auth_file="unused",
                source_revision=REVISION,
                deployment_revision=REVISION,
                case_ids=["ORS-001", "ORS-009"],
            )
        client.assert_not_called()

    def test_wait_for_pending_rejects_mismatched_cases_and_unusable_handles(self):
        case_id = str(CASE_ID)
        client = object.__new__(LiveClient)
        created = {"id": case_id, "status": "created"}
        client._read_for_poll = AsyncMock(return_value={"id": str(uuid4()), "status": "pending"})
        with (
            patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0),
            self.assertRaisesRegex(RuntimeError, "different case"),
        ):
            client.wait_for_pending(created)
        self.assertEqual(client._read_for_poll.await_count, 1)

        for handle, channel in (("handle", "other"), ("  ", "foundry-responses")):
            with self.subTest(handle=handle, channel=channel):
                client._read_for_poll = AsyncMock(
                    return_value={
                        "id": case_id,
                        "status": "pending",
                        "decision_handle": handle,
                        "decision_channel": channel,
                    }
                )
                with (
                    patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0),
                    self.assertRaisesRegex(RuntimeError, "invalid|unexpected"),
                ):
                    client.wait_for_pending(created)
                self.assertEqual(client._read_for_poll.await_count, 1)

        client._read_for_poll = AsyncMock(return_value={"id": case_id, "status": "pending"})
        with (
            patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0),
            self.assertRaisesRegex(RuntimeError, "polling limit"),
        ):
            client.wait_for_pending(created)
        self.assertEqual(client._read_for_poll.await_count, 30)

    def test_wait_for_pending_has_a_wall_clock_deadline_for_a_stalled_read(self):
        case_id = str(CASE_ID)
        for phase in ("response", "body"):
            with self.subTest(phase=phase):
                client = object.__new__(LiveClient)
                client.base_url = "https://api.example.test"
                client.owner = {"access_token": "synthetic-token"}
                cancelled = Event()

                class StalledStream(httpx.AsyncByteStream):
                    async def __aiter__(self):
                        try:
                            yield b'{"id":'
                            await asyncio.sleep(10)
                        finally:
                            cancelled.set()

                async def stalled_read(_request):
                    if phase == "body":
                        return httpx.Response(200, stream=StalledStream())
                    try:
                        await asyncio.sleep(10)
                    finally:
                        cancelled.set()

                real_client = httpx.AsyncClient
                transport = httpx.MockTransport(stalled_read)
                start = time.monotonic()
                with (
                    patch(
                        "tests.live_acceptance.httpx.AsyncClient",
                        side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
                    ),
                    patch("tests.live_acceptance.CASE_POLL_TIMEOUT_SECONDS", 0.1),
                    patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0),
                    self.assertRaisesRegex(TimeoutError, "polling deadline"),
                ):
                    client.wait_for_pending({"id": case_id, "status": "created"})
                self.assertTrue(cancelled.is_set())
                self.assertLess(time.monotonic() - start, 2)

    def test_poll_read_records_correlation_and_reaches_pending(self):
        case_id = str(CASE_ID)
        request_id = str(uuid4())
        trace_id = "a" * 32
        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.owner = {"access_token": "synthetic-token"}
        client.deployment_revision = REVISION
        client.correlations = []

        async def pending(_request):
            return httpx.Response(
                200,
                headers={
                    "X-Correlation-ID": request_id,
                    "traceparent": f"00-{trace_id}-{'b' * 16}-01",
                },
                json={
                    "id": case_id,
                    "status": "pending",
                    "decision_handle": "handle",
                    "decision_channel": "foundry-responses",
                },
            )

        real_client = httpx.AsyncClient
        with (
            patch(
                "tests.live_acceptance.httpx.AsyncClient",
                side_effect=lambda **kwargs: real_client(
                    transport=httpx.MockTransport(pending), **kwargs
                ),
            ),
            patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0),
            patch.dict("os.environ", {"AGENT_VERSION": "1"}),
        ):
            result = client.wait_for_pending({"id": case_id, "status": "created"})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(client.correlations[0]["request_id"], request_id)
        self.assertEqual(client.correlations[0]["trace_id"], trace_id)

    def test_poll_read_does_not_follow_redirect_with_bearer(self):
        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.owner = {"access_token": "synthetic-canary"}
        observed = []

        async def redirect(request):
            observed.append((str(request.url), request.headers.get("authorization")))
            return httpx.Response(302, headers={"Location": "https://attacker.example/steal"})

        real_client = httpx.AsyncClient
        with (
            patch(
                "tests.live_acceptance.httpx.AsyncClient",
                side_effect=lambda **kwargs: real_client(
                    transport=httpx.MockTransport(redirect), **kwargs
                ),
            ),
            self.assertRaisesRegex(RuntimeError, "redirects are not permitted"),
        ):
            asyncio.run(client._read_for_poll(str(CASE_ID)))
        self.assertEqual(
            observed,
            [(f"https://api.example.test/api/cases/{CASE_ID}", "Bearer synthetic-canary")],
        )

    def test_poll_does_not_mislabel_an_early_transport_timeout_as_deadline_expiry(self):
        client = object.__new__(LiveClient)
        client._read_for_poll = AsyncMock(side_effect=TimeoutError("transport timeout"))
        with (
            patch("tests.live_acceptance.CASE_POLL_INTERVAL_SECONDS", 0),
            self.assertRaisesRegex(TimeoutError, "^transport timeout$"),
        ):
            client.wait_for_pending({"id": str(CASE_ID), "status": "created"})

    def test_replayed_submission_is_not_a_hosted_start_correlation(self):
        case_id = str(CASE_ID)
        first_request_id = str(uuid4())
        replay_request_id = str(uuid4())
        adapter = object.__new__(LiveHostedFailureAdapter)
        adapter.client = Mock()
        adapter.client.correlations = [
            {
                "request_id": first_request_id,
                "case_id": case_id,
                "trace_id": "b" * 32,
                "agent_version": "1",
                "deployment_revision": REVISION,
                "http_status": 200,
                "hosted_phase": "start",
            },
            {
                "request_id": replay_request_id,
                "case_id": case_id,
                "trace_id": "a" * 32,
                "agent_version": "1",
                "deployment_revision": REVISION,
                "http_status": 200,
                "hosted_phase": "start",
            },
        ]
        adapter.client.control.return_value = {
            "conversation_id": "conversation-1",
            "start_claim_request_id": first_request_id,
        }
        with patch.dict(
            "os.environ", {"HOSTED_AGENT_NAME": "synthetic-agent", "HOSTED_AGENT_VERSION": "1"}
        ):
            result = adapter.correlations()
        self.assertEqual(result[0]["hosted_phase"], "start")
        self.assertEqual(
            result[0]["extensions"]["producer"]["hosted_start_claim_request_id"], first_request_id
        )
        self.assertNotIn("hosted_phase", result[1])

    def test_live_client_uses_response_correlation_id_for_telemetry_pair(self):
        case_id = "20000000-0000-4000-8000-000000000002"
        request_id = "30000000-0000-4000-8000-000000000003"
        trace_id = "4" * 32

        class Response:
            status = 200
            headers = {
                "X-Correlation-ID": request_id,
                "traceparent": f"00-{trace_id}-{'5' * 16}-01",
            }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def read():
                return f'{{"id":"{case_id}"}}'.encode()

        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.opener = Mock()
        client.opener.open.return_value = Response()
        client.deployment_revision = REVISION
        client.correlations = []
        with (
            patch.dict("os.environ", {"AGENT_VERSION": "1"}),
        ):
            status, _, _ = client.request(
                "POST",
                "/api/cases",
                {"access_token": "token"},
                body={"synthetic": True},
            )

        self.assertEqual(status, 200)
        self.assertEqual(
            client.correlations,
            [
                {
                    "request_id": request_id,
                    "case_id": case_id,
                    "trace_id": trace_id,
                    "agent_version": "1",
                    "deployment_revision": REVISION,
                    "http_status": 200,
                }
            ],
        )
        self.assertIs(type(client.correlations[0]["http_status"]), int)

    def test_live_client_records_http_status_for_denied_requests(self):
        case_id = "20000000-0000-4000-8000-000000000002"
        request_id = "30000000-0000-4000-8000-000000000003"
        trace_id = "4" * 32

        headers = {
            "X-Correlation-ID": request_id,
            "traceparent": f"00-{trace_id}-{'5' * 16}-01",
        }

        client = object.__new__(LiveClient)
        client.base_url = "https://api.example.test"
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.HTTPError(
            "https://api.example.test/api/cases",
            403,
            "Forbidden",
            headers,
            io.BytesIO(f'{{"id":"{case_id}"}}'.encode()),
        )
        client.deployment_revision = REVISION
        client.correlations = []
        with (
            patch.dict("os.environ", {"AGENT_VERSION": "1"}),
        ):
            status, _, _ = client.request(
                "POST",
                "/api/cases",
                {"access_token": "token"},
                body={"synthetic": True},
            )

        self.assertEqual(status, 403)
        self.assertEqual(client.correlations[0]["http_status"], 403)
        self.assertIs(type(client.correlations[0]["http_status"]), int)

    def test_controls_are_revision_bound_and_one_shot(self):
        faults = AcceptanceFaults(enabled=True, deployment_revision=REVISION)
        faults.authorize_revision(REVISION)
        with self.assertRaises(PermissionError):
            faults.authorize_revision("b" * 40)

        faults.set_ack_fault(CASE_ID, "decision-ack-lost", True)
        self.assertEqual(faults.armed(CASE_ID), ["decision-ack-lost"])
        self.assertTrue(faults.consume_ack_fault(CASE_ID, "claim-decision"))
        self.assertFalse(faults.consume_ack_fault(CASE_ID, "claim-decision"))
        self.assertEqual(faults.observed(CASE_ID), ["decision-ack-lost"])

    def test_disabled_controls_fail_closed(self):
        faults = AcceptanceFaults(enabled=False, deployment_revision=REVISION)
        with self.assertRaises(PermissionError):
            faults.authorize_revision(REVISION)

    def test_acceptance_mode_requires_hosted_runtime(self):
        with self.assertRaisesRegex(ValueError, "only in hosted mode"):
            Settings(
                tenant_id="11111111-1111-4111-8111-111111111111",
                api_client_id="22222222-2222-4222-8222-222222222222",
                database_url="postgresql://test",
                checkpoint_root=Path("checkpoints"),
                host_mode="local",
                acceptance_mode=True,
            )

    def test_route_authorization_requires_role_and_exact_revision(self):
        store = object.__new__(OrderResolutionStore)
        store.acceptance_faults = AcceptanceFaults(
            enabled=True,
            deployment_revision=REVISION,
        )
        service = object.__new__(OrderResolutionService)
        service.store = store

        operator = AuthenticatedRequest(
            Principal(
                "tenant",
                "operator",
                frozenset({"workflow.write"}),
                frozenset({"Acceptance.Operator"}),
            ),
            "token",
        )
        self.assertEqual(_authorized(operator, service, REVISION), (store, store.acceptance_faults))

        unauthorized = AuthenticatedRequest(
            Principal("tenant", "user", frozenset({"workflow.write"}), frozenset()),
            "token",
        )
        with self.assertRaises(AccessDenied):
            _authorized(unauthorized, service, REVISION)
        with self.assertRaises(AccessDenied):
            _authorized(operator, service, "b" * 40)

    def test_snapshot_uses_case_payload_for_proposal_money(self):
        store = object.__new__(OrderResolutionStore)
        store.get = lambda _case_id: Case(
            id=CASE_ID,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload={
                "proposal": {
                    "amount": "7.90",
                    "currency": "USD",
                }
            },
            status="completed",
            decision=None,
            request_id=None,
            checkpoint_id=None,
            terminal_checkpoint_id="terminal",
            execution_complete=True,
            failure_code=None,
        )
        store.get_current_proposal = lambda _case_id: Proposal(
            case_id=str(CASE_ID),
            proposal_version=1,
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            input_digest="1" * 64,
            policy_evidence_digest="2" * 64,
            policy_version="POLICY-LATE@1",
            action="partial_refund_10",
            destination_id="synthetic-refund",
            approval_required=False,
            reason_codes=("late_delivery",),
            decision_handle_digest=None,
            decision_expires_at=None,
            decision_channel=None,
        )
        store.connect = FakeConnection

        snapshot = store.acceptance_snapshot(CASE_ID)

        self.assertEqual(snapshot["proposal"]["amount"], "7.90")
        self.assertEqual(snapshot["proposal"]["currency"], "USD")
        self.assertEqual(snapshot["counts"]["effects"], 1)
        self.assertTrue(snapshot["execution_complete"])
        self.assertIsNone(snapshot["failure_code"])
        self.assertEqual(snapshot["counts"]["approval_requests"], 0)

    def test_case_control_supports_fail_closed_cases_without_hosted_binding(self):
        store = object.__new__(OrderResolutionStore)
        store.acceptance_faults = AcceptanceFaults(
            enabled=True,
            deployment_revision=REVISION,
        )

        def missing_binding(_case_id):
            raise NotFound("The hosted platform binding is not available.")

        store.acceptance_binding = missing_binding
        store.acceptance_start_claim_request_id = lambda _case_id: None
        store.acceptance_snapshot = lambda _case_id: {
            "status": "failed",
            "counts": {"effects": 0},
        }
        service = object.__new__(OrderResolutionService)
        service.store = store
        operator = AuthenticatedRequest(
            Principal(
                "tenant",
                "operator",
                frozenset({"workflow.read"}),
                frozenset({"Acceptance.Operator"}),
            ),
            "token",
        )

        result = case_control(CASE_ID, REVISION, operator, service)

        self.assertIsNone(result["conversation_id"])
        self.assertIsNone(result["platform_session_id"])
        self.assertEqual(result["snapshot"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
