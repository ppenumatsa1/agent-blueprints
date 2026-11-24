import asyncio
import io
import json
import logging
import os
import secrets
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import httpx
import jwt
import psycopg
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql

from app.api.middleware import install_request_middleware
from app.application import ApplicationComponents
from app.composition import create_app
from app.config import Settings
from app.infrastructure.delegation import OnBehalfOf
from app.domain.errors import (
    AccessDenied,
    AuthenticationFailed,
    AuthenticationUnavailable,
    DelegationError,
    HistoryScanLimitExceeded,
)
from app.domain.models import Case, Principal
from app.infrastructure.identity import AuthenticatedRequest, EntraIdentity
from app.infrastructure.migrations import upgrade
from app.domain.policy import CaseAccessPolicy, JsonObjectRules
from app.infrastructure.store import PostgresStore
from app.infrastructure.telemetry import Telemetry
from app.usecases.service import WorkflowService
from tests.fixture_application import FixtureAction, action_count, initialize_fixture


TENANT = "10000000-0000-4000-8000-000000000001"
API = "20000000-0000-4000-8000-000000000002"
OWNER = "30000000-0000-4000-8000-000000000003"
REVIEWER = "40000000-0000-4000-8000-000000000004"
STRANGER = "50000000-0000-4000-8000-000000000005"
HOSTED_SERVICE = "60000000-0000-4000-8000-000000000006"
HOSTED_SERVICE_ROLE = "Hosted.Workflow.Invoke"


def scoped_url(dsn: str, schema: str) -> str:
    parts = urlsplit(dsn)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("options", f"-csearch_path={schema}"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class TokenFixture:
    def __init__(self):
        self.first = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.second = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def token(
        self,
        subject=OWNER,
        scopes="workflow.read workflow.write",
        roles=None,
        key=None,
        kid="one",
        **changes,
    ):
        now = int(time.time())
        claims = {
            "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "aud": API,
            "tid": TENANT,
            "oid": subject,
            "sub": "synthetic-subject",
            "roles": roles or [],
            "ver": "2.0",
            "iat": now - 5,
            "nbf": now - 5,
            "exp": now + 300,
        }
        if scopes is not None:
            claims["scp"] = scopes
        claims.update(changes)
        return jwt.encode(claims, key or self.first, algorithm="RS256", headers={"kid": kid})

    def jwk(self, key, kid):
        value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        value.update({"kid": kid, "use": "sig", "alg": "RS256"})
        return value

    def client(self):
        return StaticKeys({"one": self.first.public_key(), "two": self.second.public_key()})


class StaticKeys:
    def __init__(self, keys):
        self.keys = keys

    def get_signing_key_from_jwt(self, token):
        kid = jwt.get_unverified_header(token)["kid"]
        if kid not in self.keys:
            raise jwt.PyJWKClientError("Unknown signing key.")
        return type("SigningKey", (), {"key": self.keys[kid]})()


class ActivityStreamTests(unittest.TestCase):
    def setUp(self):
        from app.api.errors import install_exception_handlers
        from app.api.routes.activity_stream import router

        principal = Principal(TENANT, OWNER, frozenset({"workflow.read"}), frozenset())
        self.identity = Mock()
        self.identity.authenticate.return_value = AuthenticatedRequest(principal, "private-token")
        self.store = PostgresStore("postgresql://localhost/test", pool_max_size=2)
        self.store.get_for_activity_stream = AsyncMock(
            return_value=Case(
                id=uuid4(),
                tenant_id=TENANT,
                owner_id=OWNER,
                reviewer_id=REVIEWER,
                payload={},
                status="pending",
                decision=None,
                request_id=None,
                checkpoint_id=None,
                terminal_checkpoint_id=None,
                execution_complete=False,
                failure_code=None,
            )
        )
        self.service = WorkflowService(self.store, Mock(), Mock(), CaseAccessPolicy())
        authenticate = patch(
            "app.api.routes.activity_stream.stream_authenticate",
            new=AsyncMock(side_effect=lambda request, token: self.identity.authenticate(token)),
        )
        authenticate.start()
        self.addCleanup(authenticate.stop)
        self.app = FastAPI()
        self.app.state.identity = self.identity
        self.app.state.service = self.service
        install_exception_handlers(self.app)
        self.app.include_router(router, prefix="/api")
        self.client = TestClient(self.app)
        self.path = f"/api/cases/{uuid4()}/activity/stream"
        self.headers = {"Authorization": "Bearer private-token"}

    def test_requires_auth_and_rejects_bad_resume_cursor(self):
        self.assertEqual(self.client.get(self.path).status_code, 401)
        response = self.client.get(self.path, headers={**self.headers, "Last-Event-ID": "bad!"})
        self.assertEqual(response.status_code, 422)
        self.store.get_for_activity_stream.assert_not_called()

    def test_stream_capacity_rejects_before_authentication(self):
        from app.api.routes.activity_stream import (
            MAX_CONCURRENT_ACTIVITY_STREAMS,
            _activity_stream_runtime,
        )

        acquired = 0
        try:
            for _ in range(MAX_CONCURRENT_ACTIVITY_STREAMS):
                self.assertTrue(_activity_stream_runtime.try_acquire_stream())
                acquired += 1
            response = self.client.get(self.path, headers=self.headers)
            self.assertEqual(response.status_code, 503)
            self.identity.authenticate.assert_not_called()
        finally:
            for _ in range(acquired):
                _activity_stream_runtime.release_stream()

    def test_unknown_store_disables_stream(self):
        self.service.store = Mock()
        response = self.client.get(self.path, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.store.get_for_activity_stream.assert_not_called()

    def test_overridden_store_connect_disables_stream(self):
        class CustomStore(PostgresStore):
            def connect(self):
                return super().connect()

        self.service.store = CustomStore("postgresql://localhost/test")
        response = self.client.get(self.path, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.store.get_for_activity_stream.assert_not_called()

    def test_async_io_saturation_returns_503_then_recovers(self):
        from app.api.routes.activity_stream import _activity_stream_runtime

        with patch.object(_activity_stream_runtime, "_worker_slots", BoundedSemaphore(1)):
            _activity_stream_runtime._worker_slots.acquire()
            response = self.client.get(self.path, headers=self.headers)
            _activity_stream_runtime._worker_slots.release()
        self.assertEqual(response.status_code, 503)
        self.store.get_for_activity_stream.assert_not_called()
        with (
            patch("app.api.routes.activity_stream.STREAM_SECONDS", 1),
            patch("app.api.routes.activity_stream.HEARTBEAT_SECONDS", 1),
            patch("app.api.routes.activity_stream.asyncio.sleep", new_callable=AsyncMock),
        ):
            response = self.client.get(self.path, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: activity.refresh", response.text)

    def test_reauthorizes_each_tick_and_stops_on_policy_revocation(self):
        case = self.store.get_for_activity_stream.return_value
        self.store.get_for_activity_stream.side_effect = [
            case,
            case,
            replace(case, owner_id=STRANGER, reviewer_id=STRANGER),
        ]
        with (
            patch("app.api.routes.activity_stream.STREAM_SECONDS", 2),
            patch("app.api.routes.activity_stream.HEARTBEAT_SECONDS", 1),
            patch("app.api.routes.activity_stream.asyncio.sleep", new_callable=AsyncMock),
        ):
            response = self.client.get(self.path, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.text.count("event: activity.refresh"), 1)
        self.assertIn("event: unavailable", response.text)
        self.assertNotIn("private", response.text)
        self.assertEqual(self.identity.authenticate.call_count, 3)
        self.assertEqual(self.store.get_for_activity_stream.call_count, 3)

    def test_initial_policy_denial_is_an_http_error(self):
        self.store.get_for_activity_stream.return_value = replace(
            self.store.get_for_activity_stream.return_value,
            owner_id=STRANGER,
            reviewer_id=STRANGER,
        )
        response = self.client.get(self.path, headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("private-canary", response.text)

    def test_valid_resume_hint_forces_fresh_authorized_refresh_and_bounded_stream(self):
        from app.usecases.history import _encode_cursor

        cursor = _encode_cursor("activity", datetime.now(timezone.utc), 1, None)
        with (
            patch("app.api.routes.activity_stream.STREAM_SECONDS", 2),
            patch("app.api.routes.activity_stream.HEARTBEAT_SECONDS", 1),
            patch("app.api.routes.activity_stream.asyncio.sleep", new_callable=AsyncMock),
        ):
            response = self.client.get(self.path, headers={**self.headers, "Last-Event-ID": cursor})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.count("event: activity.refresh"), 2)
        self.assertEqual(self.store.get_for_activity_stream.call_count, 3)
        self.assertNotIn(cursor, response.text)

    def test_token_is_revalidated_until_it_expires(self):
        identity = self.identity.authenticate.return_value
        self.identity.authenticate.side_effect = [
            identity,
            identity,
            AuthenticationFailed("private-canary"),
        ]
        with (
            patch("app.api.routes.activity_stream.STREAM_SECONDS", 2),
            patch("app.api.routes.activity_stream.HEARTBEAT_SECONDS", 1),
            patch("app.api.routes.activity_stream.asyncio.sleep", new_callable=AsyncMock),
        ):
            response = self.client.get(self.path, headers=self.headers)
        self.assertEqual(response.text.count("event: activity.refresh"), 1)
        self.assertIn("event: unavailable", response.text)
        self.assertNotIn("private-canary", response.text)
        self.assertEqual(self.store.get_for_activity_stream.call_count, 2)

    def test_slow_tick_ends_stream_at_deadline_with_retry(self):
        case = self.store.get_for_activity_stream.return_value
        cancelled = []

        async def read(case_id):
            if self.store.get_for_activity_stream.call_count == 1:
                return case
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

        self.store.get_for_activity_stream.side_effect = read
        with (
            patch("app.api.routes.activity_stream.STREAM_SECONDS", 0.1),
            patch("app.api.routes.activity_stream.HEARTBEAT_SECONDS", 0.1),
        ):
            response = self.client.get(self.path, headers=self.headers)
        self.assertIn("event: retry", response.text)
        self.assertNotIn("event: activity.refresh", response.text)
        self.assertEqual(self.store.get_for_activity_stream.call_count, 2)
        self.assertEqual(cancelled, [True])

    def test_managed_identity_and_custom_policy_fall_back_without_sync_work(self):
        self.store._connector.options = replace(
            self.store._connector.options, auth_mode="managed-identity"
        )
        self.assertEqual(self.client.get(self.path, headers=self.headers).status_code, 503)
        self.identity.authenticate.assert_not_called()
        self.store.get_for_activity_stream.assert_not_called()
        self.store._connector.options = replace(self.store._connector.options, auth_mode="password")
        self.service.policy = Mock()
        self.assertEqual(self.client.get(self.path, headers=self.headers).status_code, 503)
        self.identity.authenticate.assert_not_called()

    def test_database_failure_does_not_expose_details(self):
        self.store.get_for_activity_stream.side_effect = psycopg.OperationalError("private-canary")
        response = self.client.get(self.path, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-canary", response.text)


class ActivityStreamRuntimeTests(unittest.TestCase):
    def test_timeout_cancels_work_and_releases_capacity(self):
        from app.api.routes.activity_stream import (
            ActivityStreamCapacityError,
            ActivityStreamRuntime,
        )

        runtime = ActivityStreamRuntime(workers=1, max_streams=1)
        cleaned = []

        async def blocked_work():
            try:
                with self.assertRaises(ActivityStreamCapacityError):
                    await runtime.call(blocked_work, timeout=1)
                await asyncio.Event().wait()
            finally:
                cleaned.append(True)

        async def exercise():
            with self.assertRaises(TimeoutError):
                await runtime.call(blocked_work, timeout=0.01)
            self.assertEqual(cleaned, [True])
            self.assertEqual(await runtime.call(AsyncMock(return_value=42), timeout=1), 42)
            self.assertEqual(len(asyncio.all_tasks()), 1)

        self.assertTrue(runtime.try_acquire_stream())
        self.assertFalse(runtime.try_acquire_stream())
        runtime.release_stream()
        asyncio.run(exercise())

    def test_disconnect_cancels_work_and_releases_capacity(self):
        from app.api.routes.activity_stream import ActivityStreamRuntime

        runtime = ActivityStreamRuntime(workers=1)

        async def exercise():
            started = asyncio.Event()
            cleaned = asyncio.Event()

            async def blocked_work():
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()

            task = asyncio.create_task(runtime.call(blocked_work, timeout=1))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(cleaned.is_set())
            await runtime.call(AsyncMock(), timeout=1)
            self.assertEqual(len(asyncio.all_tasks()), 1)

        asyncio.run(exercise())


class StreamIdentityTests(unittest.TestCase):
    def test_async_keys_preserve_delegated_token_validation_without_sync_jwks(self):
        from app.api.routes.activity_stream import stream_authenticate

        tokens = TokenFixture()
        identity = EntraIdentity(
            Settings(TENANT, API, "postgresql://localhost/test", Path("test-checkpoints")),
            Mock(),
        )
        request = Mock()
        request.app.state.identity = identity

        async def exercise():
            fetch = Mock(
                return_value=httpx.Response(200, json={"keys": [tokens.jwk(tokens.first, "one")]})
            )
            transport = httpx.MockTransport(fetch)
            client = httpx.AsyncClient(transport=transport)
            with patch(
                "app.api.routes.activity_stream.httpx.AsyncClient", return_value=client
            ) as factory:
                with self.assertRaises(AuthenticationFailed):
                    await stream_authenticate(request, "malformed")
                factory.assert_not_called()
                actor = await stream_authenticate(request, tokens.token())
                await stream_authenticate(request, tokens.token())
                with self.assertRaises(AuthenticationFailed):
                    await stream_authenticate(request, tokens.token(aud="wrong-audience"))
            self.assertEqual(actor.principal.subject, OWNER)
            identity.jwks.get_signing_key_from_jwt.assert_not_called()
            fetch.assert_called_once()
            self.assertTrue(client.is_closed)

        asyncio.run(exercise())

    def test_key_rotation_is_refresh_throttled_and_expired_keys_fail_closed(self):
        from app.api.routes.activity_stream import StreamSigningKeyCache, StreamSigningKeys

        tokens = TokenFixture()
        identity = EntraIdentity(
            Settings(TENANT, API, "postgresql://localhost/test", Path("test-checkpoints"))
        )
        first = StreamSigningKeys({"keys": [tokens.jwk(tokens.first, "one")]})
        second = StreamSigningKeys({"keys": [tokens.jwk(tokens.second, "two")]})
        cache = StreamSigningKeyCache(identity)

        async def exercise():
            with patch(
                "app.api.routes.activity_stream.stream_signing_keys",
                new=AsyncMock(
                    side_effect=[first, second, AuthenticationUnavailable("unavailable")]
                ),
            ) as fetch:
                self.assertIs(await cache.get("one"), first)
                self.assertIs(await cache.get("two"), first)
                with self.assertRaises(AuthenticationFailed):
                    EntraIdentity(identity.settings, first).authenticate(
                        tokens.token(key=tokens.second, kid="two")
                    )
                fetch.assert_awaited_once()
                cache.refresh_after = 0
                self.assertIs(await cache.get("two"), second)
                actor = EntraIdentity(identity.settings, second).authenticate(
                    tokens.token(key=tokens.second, kid="two")
                )
                self.assertEqual(actor.principal.subject, OWNER)
                cache.expires_at = 0
                with self.assertRaises(AuthenticationUnavailable):
                    await cache.get("two")
                self.assertEqual(fetch.await_count, 2)
                cache.refresh_after = 0
                with self.assertRaises(AuthenticationUnavailable):
                    await cache.get("two")
                with self.assertRaises(AuthenticationUnavailable):
                    await cache.get("two")
                self.assertEqual(fetch.await_count, 3)

        asyncio.run(exercise())

    def test_concurrent_cold_cache_fetch_is_bounded_and_cancellation_releases_slot(self):
        from app.api.routes.activity_stream import StreamSigningKeyCache, StreamSigningKeys

        tokens = TokenFixture()
        identity = EntraIdentity(
            Settings(TENANT, API, "postgresql://localhost/test", Path("test-checkpoints"))
        )
        keys = StreamSigningKeys({"keys": [tokens.jwk(tokens.first, "one")]})
        cache = StreamSigningKeyCache(identity)

        async def exercise():
            started = asyncio.Event()

            async def blocked_fetch(identity):
                started.set()
                await asyncio.Event().wait()

            with patch(
                "app.api.routes.activity_stream.stream_signing_keys",
                new=AsyncMock(side_effect=blocked_fetch),
            ) as fetch:
                task = asyncio.create_task(cache.get("one"))
                await started.wait()
                with self.assertRaises(AuthenticationUnavailable):
                    await cache.get("one")
                fetch.assert_awaited_once()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                cache.refresh_after = 0
                fetch.side_effect = None
                fetch.return_value = keys
                self.assertIs(await cache.get("one"), keys)
                self.assertEqual(len(asyncio.all_tasks()), 1)

        asyncio.run(exercise())

    def test_jwks_read_is_cancellable_and_closes_http_resources(self):
        from app.api.routes.activity_stream import ActivityStreamRuntime, stream_signing_keys

        closed = []

        class StalledBody(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"keys":['
                await asyncio.Event().wait()

            async def aclose(self):
                closed.append(True)

        async def exercise():
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, stream=StalledBody())
                )
            )
            identity = EntraIdentity(
                Settings(TENANT, API, "postgresql://localhost/test", Path("test-checkpoints"))
            )
            with patch("app.api.routes.activity_stream.httpx.AsyncClient", return_value=client):
                with self.assertRaises(TimeoutError):
                    await ActivityStreamRuntime().call(stream_signing_keys, identity, timeout=0.01)
            self.assertEqual(closed, [True])
            self.assertTrue(client.is_closed)
            self.assertEqual(len(asyncio.all_tasks()), 1)

        asyncio.run(exercise())

    def test_invalid_or_oversized_jwks_fails_closed(self):
        from app.api.routes.activity_stream import stream_signing_keys

        async def exercise():
            identity = EntraIdentity(
                Settings(TENANT, API, "postgresql://localhost/test", Path("test-checkpoints"))
            )
            for body in (b"{}", b"[]", b'{"keys":null}', b"x" * 262_145, b"not-json"):
                client = httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
                )
                with patch("app.api.routes.activity_stream.httpx.AsyncClient", return_value=client):
                    with self.assertRaises(AuthenticationUnavailable):
                        await stream_signing_keys(identity)
                self.assertTrue(client.is_closed)

        asyncio.run(exercise())


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = TokenFixture()

    def setUp(self):
        self.settings = Settings(
            TENANT,
            API,
            "postgresql://localhost/test",
            Path("test-checkpoints"),
            api_app_id_uri=f"api://{API}",
            hosted_service_principal_id=HOSTED_SERVICE,
            hosted_service_app_role=HOSTED_SERVICE_ROLE,
        )
        self.identity = EntraIdentity(self.settings, self.tokens.client())

    def test_signature_issuer_audience_tenant_lifetime_and_delegated_claims(self):
        valid = self.identity.authenticate(self.tokens.token())
        self.assertEqual(valid.principal.subject, OWNER)
        self.assertNotIn(valid.access_token, repr(valid))
        invalid = [
            self.tokens.token(key=self.tokens.second),
            self.tokens.token(aud="60000000-0000-4000-8000-000000000006"),
            self.tokens.token(iss="https://invalid.example/v2.0"),
            self.tokens.token(tid="70000000-0000-4000-8000-000000000007"),
            self.tokens.token(exp=int(time.time()) - 10),
            self.tokens.token(nbf=int(time.time()) + 600),
            self.tokens.token(ver="1.0"),
            self.tokens.token(oid="not-a-uuid"),
            self.tokens.token(scp=""),
            self.tokens.token(roles="Workflow.Approver"),
            "not-a-token",
        ]
        for token in invalid:
            with self.subTest(token=invalid.index(token)):
                with self.assertRaises(AuthenticationFailed):
                    self.identity.authenticate(token)

    def test_signing_key_rotation_uses_the_configured_jwks_endpoint(self):
        identity = EntraIdentity(self.settings)
        identity.jwks.cooldown_duration = 0
        documents = [
            {"keys": [self.tokens.jwk(self.tokens.first, "one")]},
            {"keys": [self.tokens.jwk(self.tokens.second, "two")]},
        ]
        opener = Mock()
        opener.open.side_effect = [
            io.BytesIO(json.dumps(document).encode("utf-8")) for document in documents
        ]
        with patch("urllib.request.build_opener", return_value=opener):
            identity.authenticate(self.tokens.token())
            identity.authenticate(self.tokens.token(key=self.tokens.second, kid="two"))
        self.assertEqual(opener.open.call_count, 2)
        for call in opener.open.call_args_list:
            request = call.args[0]
            self.assertEqual(
                request.full_url, f"https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys"
            )

    def test_service_identity_requires_app_role_authorized_principal_and_no_user_scope(self):
        valid = self.identity.authenticate_service(
            self.tokens.token(
                subject=HOSTED_SERVICE,
                scopes=None,
                roles=[HOSTED_SERVICE_ROLE],
                aud=f"api://{API}",
            )
        )
        self.assertEqual(valid.principal.subject, HOSTED_SERVICE)
        invalid = [
            self.tokens.token(
                subject=HOSTED_SERVICE,
                scopes=None,
                roles=[],
            ),
            self.tokens.token(
                subject=STRANGER,
                scopes=None,
                roles=[HOSTED_SERVICE_ROLE],
            ),
            self.tokens.token(
                subject=HOSTED_SERVICE,
                scopes="workflow.read",
                roles=[HOSTED_SERVICE_ROLE],
            ),
        ]
        for token in invalid:
            with self.subTest(token=invalid.index(token)):
                with self.assertRaises(AuthenticationFailed):
                    self.identity.authenticate_service(token)

    def test_jwks_network_failure_is_not_accepted(self):
        client = Mock()
        client.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientConnectionError("offline")
        with self.assertRaises(AuthenticationUnavailable):
            EntraIdentity(self.settings, client).authenticate(self.tokens.token())

    def test_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_environment()
        with self.assertRaises(ValueError):
            replace(self.settings, tenant_id="")
        with self.assertRaises(ValueError):
            replace(self.settings, api_client_id="")
        with self.assertRaises(ValueError):
            replace(self.settings, host_mode="foundry")
        with self.assertRaises(ValueError):
            replace(self.settings, cors_origins=("*",))
        with self.assertRaises(ValueError):
            replace(self.settings, cors_origins=("http://example.test",))
        with self.assertRaises(ValueError):
            replace(self.settings, obo_enabled=True)

    def test_obo_is_opt_in_scope_limited_and_uses_validated_user_token(self):
        validated = self.identity.authenticate(self.tokens.token())
        scope = "https://graph.microsoft.com/User.Read"
        with self.assertRaises(DelegationError):
            OnBehalfOf(self.settings).exchange(validated, [scope])
        secret = secrets.token_urlsafe(24)
        configured = replace(
            self.settings,
            obo_enabled=True,
            obo_client_secret=secret,
            obo_allowed_scopes=(scope,),
        )
        self.assertNotIn(secret, repr(configured))
        client = Mock()
        client.acquire_token_on_behalf_of.return_value = {"access_token": "test-downstream-token"}
        factory = Mock(return_value=client)
        obo = OnBehalfOf(configured, factory)
        self.assertEqual(obo.exchange(validated, [scope]), "test-downstream-token")
        client.acquire_token_on_behalf_of.assert_called_once_with(
            user_assertion=validated.access_token, scopes=[scope]
        )
        with self.assertRaises(DelegationError):
            obo.exchange(validated, ["https://graph.microsoft.com/Mail.Read"])
        client.acquire_token_on_behalf_of.return_value = {"error": "invalid_grant"}
        with self.assertRaises(DelegationError):
            obo.exchange(validated, [scope])


class ApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("MAF_TEST_DATABASE_URL")
        if not cls.dsn:
            raise RuntimeError(
                "MAF_TEST_DATABASE_URL must point to an isolated PostgreSQL test database."
            )
        cls.tokens = TokenFixture()

    def setUp(self):
        self.schema = "test_" + uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self._drop_schema)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(
            TENANT,
            API,
            scoped_url(self.dsn, self.schema),
            Path(self.temp.name) / "checkpoints",
            cors_origins=("http://localhost:3000",),
        )
        self.store = PostgresStore(self.settings.database_url)
        upgrade(self.settings.database_url)
        self.components = ApplicationComponents(
            JsonObjectRules(), CaseAccessPolicy(), FixtureAction(), initialize_fixture
        )
        self.identity = EntraIdentity(self.settings, self.tokens.client())
        from app.api.routes.activity_stream import StreamSigningKeys

        keys = patch(
            "app.api.routes.activity_stream.stream_signing_keys",
            new=AsyncMock(
                return_value=StreamSigningKeys(
                    {
                        "keys": [
                            self.tokens.jwk(self.tokens.first, "one"),
                            self.tokens.jwk(self.tokens.second, "two"),
                        ],
                    }
                )
            ),
        )
        keys.start()
        self.addCleanup(keys.stop)
        self.owner_token = self.tokens.token()
        self.reviewer_token = self.tokens.token(
            subject=REVIEWER, scopes="workflow.read workflow.approve", roles=["Workflow.Approver"]
        )

    def _drop_schema(self):
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def client(self):
        return TestClient(
            create_app(self.settings, self.components, store=self.store, identity=self.identity)
        )

    def test_async_stream_read_cancels_locked_query_without_borrowing_api_pool(self):
        from app.api.routes.activity_stream import ActivityStreamRuntime

        application_name = "stream_" + uuid4().hex
        self.store._connector.options = replace(
            self.store._connector.options,
            dsn=self.settings.database_url + "&application_name=" + application_name,
        )

        async def exercise():
            with psycopg.connect(self.settings.database_url) as blocker:
                blocker.execute("LOCK TABLE wf_cases IN ACCESS EXCLUSIVE MODE")
                with patch.object(self.store._pool, "connection") as pooled:
                    with self.assertRaises(TimeoutError):
                        await ActivityStreamRuntime().call(
                            self.store.get_for_activity_stream, uuid4(), timeout=0.1
                        )
                    pooled.assert_not_called()
            with psycopg.connect(self.dsn) as observer:
                remaining = observer.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE application_name = %s",
                    (application_name,),
                ).fetchone()[0]
            self.assertEqual(remaining, 0)
            self.assertEqual(len(asyncio.all_tasks()), 1)

        asyncio.run(exercise())

    def test_stream_database_has_server_deadline_and_is_read_only(self):
        async def exercise():
            async with await self.store._connector.connect_for_activity_stream() as connection:
                for setting, expected in (
                    ("statement_timeout", "5s"),
                    ("lock_timeout", "5s"),
                    ("default_transaction_read_only", "on"),
                ):
                    cursor = await connection.execute(f"SHOW {setting}")
                    self.assertEqual((await cursor.fetchone())[setting], expected)
                with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                    await connection.execute("DELETE FROM wf_cases")
                started = time.monotonic()
                with self.assertRaises(psycopg.errors.QueryCanceled):
                    await connection.execute("SELECT pg_sleep(30)")
                self.assertLess(time.monotonic() - started, 10)

        asyncio.run(exercise())

    @staticmethod
    def headers(token, key=None):
        result = {"Authorization": f"Bearer {token}"}
        if key:
            result["Idempotency-Key"] = key
        return result

    def test_unhandled_api_errors_are_generic_and_correlated(self):
        app = FastAPI()
        telemetry = Telemetry()
        self.addCleanup(telemetry.shutdown)
        install_request_middleware(app, telemetry)

        @app.get("/failure")
        def failure():
            raise RuntimeError("PRIVATE-ERROR-CANARY")

        with self.assertLogs("blueprint.api", level="ERROR") as captured:
            response = TestClient(app, raise_server_exceptions=False).get("/failure")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Internal server error."})
        self.assertTrue(response.headers["X-Correlation-ID"])
        self.assertNotIn("PRIVATE-ERROR-CANARY", response.text)
        self.assertNotIn("PRIVATE-ERROR-CANARY", " ".join(captured.output))

    def submit(self, client, token=None, reviewer=REVIEWER, payload=None):
        return client.post(
            "/api/cases",
            headers=self.headers(token or self.owner_token, str(uuid4())),
            json={"reviewer_id": reviewer, "payload": payload or {"value": 42}},
        )

    def test_token_and_record_authorization(self):
        with self.client() as client:
            self.assertEqual(client.get("/healthz").status_code, 204)
            self.assertEqual(client.get("/api/cases/" + str(uuid4())).status_code, 401)
            self.assertEqual(
                client.get("/api/cases/" + str(uuid4()), headers=self.headers("bad")).status_code,
                401,
            )
            response = self.submit(client, payload={"value": 42, "private": "SECRET-CANARY"})
            self.assertEqual(response.status_code, 200, response.text)
            case_id = response.json()["id"]
            self.assertEqual(response.json()["status"], "pending")
            stranger = self.tokens.token(
                subject=STRANGER,
                scopes="workflow.read workflow.approve",
                roles=["Workflow.Approver"],
            )
            path = f"/api/cases/{case_id}"
            self.assertEqual(client.get(path, headers=self.headers(stranger)).status_code, 403)
            self.assertEqual(
                client.post(
                    path + "/decision",
                    headers=self.headers(stranger),
                    json={"decision": "approved"},
                ).status_code,
                403,
            )
            self.assertEqual(action_count(self.store, UUID(case_id)), 0)
            self.assertEqual(
                client.get(path, headers=self.headers(self.owner_token)).status_code, 200
            )
            approved = client.post(
                path + "/decision",
                headers=self.headers(self.reviewer_token),
                json={"decision": "approved"},
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "completed")
            self.assertEqual(action_count(self.store, UUID(case_id)), 1)

    def test_history_and_activity_are_authorized_versioned_and_private(self):
        with self.client() as client:
            response = self.submit(
                client,
                payload={
                    "summary": "PAYLOAD-CANARY",
                    "request_id": "REQUEST-CANARY",
                    "checkpoint_id": "CHECKPOINT-CANARY",
                },
            )
            case_id = UUID(response.json()["id"])
            with self.store.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO wf_audit (case_id, event, actor_id)
                    VALUES (%s, 'unknown-private-event', 'ACTOR-CANARY')
                    """,
                    (case_id,),
                )

            history = client.get(
                "/api/cases?status=pending&limit=1",
                headers=self.headers(self.owner_token),
            )
            self.assertEqual(history.status_code, 200, history.text)
            self.assertEqual(history.json()["schema_version"], "workflow-history/1")
            self.assertEqual(set(history.json()), {"schema_version", "items", "next_cursor"})
            self.assertEqual(len(history.json()["items"]), 1)
            self.assertEqual(
                set(history.json()["items"][0]),
                {"id", "status", "decision", "created_at", "updated_at"},
            )
            activity = client.get(
                f"/api/cases/{case_id}/activity",
                headers=self.headers(self.owner_token),
            )
            self.assertEqual(activity.status_code, 200, activity.text)
            self.assertEqual(activity.json()["schema_version"], "workflow-activity/1")
            self.assertTrue(
                all(set(item) == {"type", "created_at"} for item in activity.json()["items"])
            )
            self.assertIn("review_requested", {item["type"] for item in activity.json()["items"]})
            with (
                patch("app.api.routes.activity_stream.STREAM_SECONDS", 1),
                patch("app.api.routes.activity_stream.HEARTBEAT_SECONDS", 1),
                patch("app.api.routes.activity_stream.asyncio.sleep", new_callable=AsyncMock),
            ):
                stream = client.get(
                    f"/api/cases/{case_id}/activity/stream",
                    headers=self.headers(self.owner_token),
                )
            self.assertEqual(stream.status_code, 200)
            self.assertIn("event: activity.refresh", stream.text)
            public_output = history.text + activity.text + stream.text
            for private_value in (
                "PAYLOAD-CANARY",
                "REQUEST-CANARY",
                "CHECKPOINT-CANARY",
                "ACTOR-CANARY",
                "unknown-private-event",
            ):
                self.assertNotIn(private_value, public_output)

            stranger = self.tokens.token(subject=STRANGER, scopes="workflow.read", roles=[])
            hidden = client.get("/api/cases", headers=self.headers(stranger))
            self.assertEqual(hidden.status_code, 200)
            self.assertEqual(hidden.json()["items"], [])
            self.assertIsNone(hidden.json()["next_cursor"])
            self.assertEqual(
                client.get(
                    f"/api/cases/{case_id}/activity", headers=self.headers(stranger)
                ).status_code,
                403,
            )
            self.assertEqual(
                client.get(
                    f"/api/cases/{case_id}/activity/stream", headers=self.headers(stranger)
                ).status_code,
                403,
            )
            self.assertEqual(
                client.get(
                    "/api/cases?status=unknown", headers=self.headers(self.owner_token)
                ).status_code,
                422,
            )
            self.assertEqual(
                client.get(
                    "/api/cases?limit=101", headers=self.headers(self.owner_token)
                ).status_code,
                422,
            )
            self.assertEqual(
                client.get(
                    "/api/cases?cursor=malformed", headers=self.headers(self.owner_token)
                ).status_code,
                422,
            )

    def test_history_scan_budget_returns_explicit_private_error(self):
        with (
            self.client() as client,
            patch.object(WorkflowService, "history", side_effect=HistoryScanLimitExceeded()),
        ):
            response = client.get("/api/cases", headers=self.headers(self.owner_token))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Workflow history scan budget exceeded."})

    def test_api_rejects_forged_expired_wrong_issuer_audience_and_tenant_tokens(self):
        invalid = (
            self.tokens.token(key=self.tokens.second),
            self.tokens.token(exp=int(time.time()) - 10),
            self.tokens.token(iss="https://invalid.example/v2.0"),
            self.tokens.token(aud="60000000-0000-4000-8000-000000000006"),
            self.tokens.token(tid="70000000-0000-4000-8000-000000000007"),
        )
        with self.client() as client:
            for token in invalid:
                with self.subTest(token=invalid.index(token)):
                    response = client.get(f"/api/cases/{uuid4()}", headers=self.headers(token))
                    self.assertEqual(response.status_code, 401)

    def test_scope_role_cross_case_and_actor_spoofing_are_rejected(self):
        with self.client() as client:
            case_id = self.submit(client).json()["id"]
            other = self.submit(client, reviewer=STRANGER).json()["id"]
            path = f"/api/cases/{case_id}/decision"
            no_role = self.tokens.token(subject=REVIEWER, scopes="workflow.approve")
            no_scope = self.tokens.token(
                subject=REVIEWER, scopes="workflow.read", roles=["Workflow.Approver"]
            )
            for token in (no_role, no_scope):
                self.assertEqual(
                    client.post(
                        path, headers=self.headers(token), json={"decision": "approved"}
                    ).status_code,
                    403,
                )
            self.assertEqual(
                client.post(
                    f"/api/cases/{other}/decision",
                    headers=self.headers(self.reviewer_token),
                    json={"decision": "approved"},
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(
                    path,
                    headers=self.headers(self.reviewer_token),
                    json={"decision": "approved", "actor": REVIEWER},
                ).status_code,
                422,
            )
            self.assertEqual(action_count(self.store, UUID(case_id)), 0)
            self.assertEqual(action_count(self.store, UUID(other)), 0)

    def test_restart_recovers_a_durable_decision(self):
        with self.client() as client:
            case_id = UUID(self.submit(client).json()["id"])
            reviewer = self.identity.authenticate(self.reviewer_token).principal
            self.store.record_decision(case_id, reviewer, "approved")
            self.assertEqual(action_count(self.store, case_id), 0)
        with self.client() as restarted:
            response = restarted.get(
                f"/api/cases/{case_id}", headers=self.headers(self.owner_token)
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "completed")
            self.assertEqual(action_count(self.store, case_id), 1)

    def test_restart_surfaces_missing_checkpoint_without_an_action(self):
        with self.client() as client:
            case_id = UUID(self.submit(client).json()["id"])
            record = self.store.get(case_id)
            reviewer = self.identity.authenticate(self.reviewer_token).principal
            self.store.record_decision(case_id, reviewer, "approved")
            (self.settings.checkpoint_root / str(case_id) / f"{record.checkpoint_id}.json").unlink()
        with self.assertLogs("blueprint.telemetry", level=logging.INFO) as logs:
            with self.client() as restarted:
                response = restarted.get(
                    f"/api/cases/{case_id}", headers=self.headers(self.owner_token)
                )
                self.assertEqual(response.json()["failure_code"], "recovery_failed")
                self.assertEqual(action_count(self.store, case_id), 0)
        self.assertNotIn(self.owner_token, " ".join(logs.output))
        self.assertIn('"event":"recovery","outcome":"failure"', " ".join(logs.output))

    def test_startup_recovery_preserves_action_failure(self):
        with self.client() as client:
            case_id = UUID(self.submit(client).json()["id"])
            reviewer = self.identity.authenticate(self.reviewer_token).principal
            self.store.record_decision(case_id, reviewer, "approved")
        self.components = replace(self.components, action=FixtureAction(fail=True))
        with self.assertLogs("blueprint.telemetry", level=logging.INFO) as logs:
            with self.client() as restarted:
                response = restarted.get(
                    f"/api/cases/{case_id}", headers=self.headers(self.owner_token)
                )
                self.assertEqual(
                    (response.json()["status"], response.json()["failure_code"]),
                    ("failed", "action_failed"),
                )
                self.assertEqual(action_count(self.store, case_id), 0)
        self.assertIn('"event":"recovery","outcome":"action_failure"', " ".join(logs.output))

    def test_rejection_and_failed_action_remain_explicit(self):
        with self.client() as client:
            case_id = UUID(self.submit(client).json()["id"])
            rejected = client.post(
                f"/api/cases/{case_id}/decision",
                headers=self.headers(self.reviewer_token),
                json={"decision": "rejected"},
            )
            self.assertEqual(rejected.status_code, 200)
            self.assertEqual(rejected.json()["status"], "rejected")
            self.assertEqual(action_count(self.store, case_id), 0)
        self.components = replace(self.components, action=FixtureAction(fail=True))
        with self.client() as client:
            case_id = UUID(self.submit(client).json()["id"])
            failed = client.post(
                f"/api/cases/{case_id}/decision",
                headers=self.headers(self.reviewer_token),
                json={"decision": "approved"},
            )
            self.assertEqual(failed.status_code, 503)
            state = client.get(f"/api/cases/{case_id}", headers=self.headers(self.owner_token))
            self.assertEqual(
                (state.json()["status"], state.json()["failure_code"]), ("failed", "action_failed")
            )
            self.assertEqual(action_count(self.store, case_id), 0)

    def test_errors_do_not_log_or_reflect_tokens_and_payload_canaries(self):
        class CanaryAction:
            def apply(self, connection, case):
                raise RuntimeError("SECRET-CANARY")

        self.components = replace(self.components, action=CanaryAction())
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)
        with self.client() as client:
            submitted = self.submit(client, payload={"private": "SECRET-CANARY"})
            case_id = submitted.json()["id"]
            failed = client.post(
                f"/api/cases/{case_id}/decision",
                headers=self.headers(self.reviewer_token),
                json={"decision": "approved"},
            )
            invalid = client.post(
                f"/api/cases/{case_id}/decision",
                headers=self.headers(self.reviewer_token),
                json={"decision": "SECRET-CANARY"},
            )
            self.assertEqual(failed.status_code, 503)
            self.assertEqual(invalid.status_code, 422)
            self.assertNotIn("SECRET-CANARY", failed.text + invalid.text)
        output = stream.getvalue()
        self.assertNotIn("SECRET-CANARY", output)
        self.assertNotIn(self.owner_token, output)
        self.assertNotIn(self.reviewer_token, output)


class SeparationOfDutiesTests(unittest.TestCase):
    def setUp(self):
        self.policy = CaseAccessPolicy()
        self.owner = Principal(
            "tenant",
            "owner",
            frozenset({"workflow.write", "workflow.approve"}),
            frozenset({"Workflow.Approver"}),
        )
        self.reviewer = replace(self.owner, subject="reviewer")
        self.case = Case(
            id=uuid4(),
            tenant_id="tenant",
            owner_id="owner",
            reviewer_id="reviewer",
            payload={},
            status="pending",
            decision=None,
            request_id=None,
            checkpoint_id=None,
            terminal_checkpoint_id=None,
            execution_complete=False,
            failure_code=None,
        )

    def test_same_identity_is_denied_even_with_write_scope_and_approver_role(self):
        with self.assertRaises(AccessDenied):
            self.policy.authorize_submission(self.owner, self.owner.subject)
        with self.assertRaises(AccessDenied):
            self.policy.authorize_decision(
                self.owner, replace(self.case, reviewer_id=self.owner.subject)
            )

    def test_distinct_reviewer_requires_matching_tenant_scope_and_role(self):
        self.policy.authorize_submission(self.owner, self.reviewer.subject)
        self.policy.authorize_decision(self.reviewer, self.case)
        for actor in (
            replace(self.reviewer, tenant_id="other"),
            replace(self.reviewer, subject="other"),
            replace(self.reviewer, scopes=frozenset()),
            replace(self.reviewer, roles=frozenset()),
        ):
            with self.subTest(actor=actor), self.assertRaises(AccessDenied):
                self.policy.authorize_decision(actor, self.case)

    def test_submission_still_requires_write_scope_and_valid_reviewer(self):
        for actor, reviewer in (
            (replace(self.owner, scopes=frozenset({"workflow.approve"})), "reviewer"),
            (replace(self.owner, tenant_id=""), "reviewer"),
            (replace(self.owner, subject=""), "reviewer"),
            (self.owner, ""),
        ):
            with self.subTest(actor=actor, reviewer=reviewer), self.assertRaises(AccessDenied):
                self.policy.authorize_submission(actor, reviewer)


if __name__ == "__main__":
    unittest.main()
