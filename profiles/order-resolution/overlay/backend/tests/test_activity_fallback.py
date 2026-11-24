import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import install_exception_handlers
from app.api.routes.activity_stream import router as stream_router
from app.api.routes.cases import router as cases_router
from app.config import Settings
from app.domain.models import Case
from app.domain.policy import CaseAccessPolicy
from app.infrastructure.identity import EntraIdentity
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.service import OrderResolutionService
from tests.test_security import API, OWNER, REVIEWER, STRANGER, TENANT, TokenFixture


class OrderResolutionActivityFallbackTests(unittest.TestCase):
    def test_unsupported_stream_never_grants_poll_access(self):
        tokens = TokenFixture()
        settings = Settings(TENANT, API, "postgresql://localhost/test", Path("test-checkpoints"))
        store = OrderResolutionStore(settings.database_url)
        case_id = uuid4()
        store.get = Mock(
            return_value=Case(
                id=case_id,
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
        store.list_activity = Mock(return_value=([], False))
        app = FastAPI()
        app.state.service = OrderResolutionService(store, Mock(), Mock(), CaseAccessPolicy())
        app.state.identity = EntraIdentity(settings, tokens.client())
        install_exception_handlers(app)
        app.include_router(stream_router, prefix="/api")
        app.include_router(cases_router, prefix="/api")
        client = TestClient(app)
        path = f"/api/cases/{case_id}/activity"
        owner = {"Authorization": f"Bearer {tokens.token()}"}
        stranger = {"Authorization": f"Bearer {tokens.token(subject=STRANGER)}"}
        invalid = {"Authorization": "Bearer invalid"}

        self.assertEqual(client.get(path + "/stream").status_code, 401)
        for headers in (owner, stranger, invalid):
            response = client.get(path + "/stream", headers=headers)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("activity.refresh", response.text)

        self.assertEqual(client.get(path, headers=owner).status_code, 200)
        self.assertEqual(client.get(path, headers=stranger).status_code, 403)
        self.assertEqual(client.get(path, headers=invalid).status_code, 401)
        store.get.return_value = replace(store.get.return_value, owner_id=STRANGER)
        self.assertEqual(client.get(path, headers=owner).status_code, 403)
        self.assertEqual(store.list_activity.call_count, 1)


if __name__ == "__main__":
    unittest.main()
