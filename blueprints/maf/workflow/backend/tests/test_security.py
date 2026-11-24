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
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

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
from app.domain.models import Principal
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
        self.service = Mock()
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
        self.service.activity.assert_not_called()

    def test_reauthorizes_each_tick_and_stops_on_policy_revocation(self):
        self.service.activity.side_effect = [None, None, AccessDenied("private-canary")]
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
        self.assertEqual(self.service.activity.call_count, 3)

    def test_initial_policy_denial_is_an_http_error(self):
        self.service.activity.side_effect = AccessDenied("private-canary")
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
        self.assertEqual(self.service.activity.call_count, 3)
        for call in self.service.activity.call_args_list:
            self.assertIsNone(call.kwargs["cursor"])
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
        self.assertEqual(self.service.activity.call_count, 2)

    def test_slow_tick_ends_stream_at_deadline_with_retry(self):
        identity = self.identity.authenticate.return_value

        def authenticate(token):
            if self.identity.authenticate.call_count == 1:
                return identity
            time.sleep(0.5)
            return identity

        self.identity.authenticate.side_effect = authenticate
        with (
            patch("app.api.routes.activity_stream.STREAM_SECONDS", 0.1),
            patch("app.api.routes.activity_stream.HEARTBEAT_SECONDS", 0.1),
        ):
            response = self.client.get(self.path, headers=self.headers)
        self.assertIn("event: retry", response.text)
        self.assertNotIn("event: activity.refresh", response.text)
        self.assertEqual(self.service.activity.call_count, 1)


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


if __name__ == "__main__":
    unittest.main()
