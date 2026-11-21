"""Test-only adapter from the synthetic order fixture to the real API and host."""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

BLUEPRINT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BLUEPRINT))

from app.application import ApplicationComponents
from app.composition import create_app
from app.config import Settings
from app.domain.errors import ActionError, CheckpointError, InvalidInput
from app.infrastructure.identity import EntraIdentity
from app.domain.policy import CaseAccessPolicy, JsonObjectRules
from app.infrastructure.store import PostgresStore
from tests.fixture_application import FixtureAction, action_count, initialize_fixture
from tests.test_security import API, OWNER, REVIEWER, STRANGER, TENANT, TokenFixture, scoped_url


class OrderFixtureRules(JsonObjectRules):
    def validate(self, payload):
        value = super().validate(payload)
        if (
            not isinstance(value.get("case_id"), str)
            or not re.fullmatch(r"CASE-[A-Z-]+", value["case_id"])
            or type(value.get("amount")) is not int
            or value["amount"] <= 100
        ):
            raise InvalidInput(
                "The synthetic fixture requires a case and an adjustment over 100 units."
            )
        return value


def run_case(data):
    if set(data) != {"case_id", "amount", "steps"} or not isinstance(data["steps"], list):
        raise ValueError("Invalid synthetic scenario input.")
    dsn = os.environ.get("MAF_TEST_DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "MAF_TEST_DATABASE_URL must point to an isolated PostgreSQL test database."
        )
    schema = "golden_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        with tempfile.TemporaryDirectory() as temporary:
            return _run_case(data, scoped_url(dsn, schema), Path(temporary) / "checkpoints")
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _run_case(data, dsn, checkpoint_root):
    tokens = TokenFixture()
    settings = Settings(TENANT, API, dsn, checkpoint_root)
    store = PostgresStore(dsn)
    action_fails = "simulate_action_failure" in data["steps"]
    components = ApplicationComponents(
        OrderFixtureRules(),
        CaseAccessPolicy(),
        FixtureAction(fail=action_fails),
        initialize_fixture,
    )
    identity = EntraIdentity(settings, tokens.client())
    owner = tokens.token(subject=OWNER)
    reviewer = tokens.token(
        subject=REVIEWER, scopes="workflow.read workflow.approve", roles=["Workflow.Approver"]
    )
    stranger = tokens.token(
        subject=STRANGER, scopes="workflow.read workflow.approve", roles=["Workflow.Approver"]
    )

    def headers(token, key=None):
        result = {"Authorization": f"Bearer {token}"}
        if key:
            result["Idempotency-Key"] = key
        return result

    def open_client():
        client = TestClient(create_app(settings, components, store=store, identity=identity))
        client.__enter__()
        return client

    def post_case(client, assigned_reviewer):
        response = client.post(
            "/api/cases",
            headers=headers(owner, str(uuid4())),
            json={
                "reviewer_id": assigned_reviewer,
                "payload": {
                    "case_id": data["case_id"],
                    "amount": data["amount"],
                    "private": "SECRET-CANARY",
                },
            },
        )
        if response.status_code != 200:
            raise AssertionError(f"Submission returned HTTP {response.status_code}.")
        return UUID(response.json()["id"])

    client = open_client()
    case_id = None
    hint_requested = False
    try:
        for step in data["steps"]:
            if step == "submit":
                if case_id is not None:
                    raise ValueError("The fixture may submit the primary case only once.")
                case_id = post_case(client, REVIEWER)
                continue
            if case_id is None:
                raise ValueError("The fixture must submit before other steps.")
            path = f"/api/cases/{case_id}/decision"
            if step in ("approve", "reject"):
                decision = "approved" if step == "approve" else "rejected"
                if (
                    step == "approve"
                    and "restart" in data["steps"]
                    and store.get(case_id).decision is None
                ):
                    # The API persists the decision, then reports the injected interruption.
                    with patch.object(
                        client.app.state.service.host,
                        "resume",
                        new=AsyncMock(side_effect=CheckpointError("Synthetic interruption.")),
                    ):
                        response = client.post(
                            path, headers=headers(reviewer), json={"decision": decision}
                        )
                    if response.status_code != 503:
                        raise AssertionError(
                            f"Interrupted approval returned HTTP {response.status_code}."
                        )
                else:
                    response = client.post(
                        path, headers=headers(reviewer), json={"decision": decision}
                    )
                    expected = 503 if action_fails and decision == "approved" else 200
                    if response.status_code != expected:
                        raise AssertionError(
                            f"Decision returned HTTP {response.status_code}, expected {expected}."
                        )
            elif step == "unauthorized_approve":
                response = client.post(
                    path, headers=headers(stranger), json={"decision": "approved"}
                )
                if response.status_code != 403:
                    raise AssertionError(
                        f"Unauthorized approval returned HTTP {response.status_code}."
                    )
            elif step == "approve_other_case":
                other = post_case(client, STRANGER)
                response = client.post(
                    f"/api/cases/{other}/decision",
                    headers=headers(reviewer),
                    json={"decision": "approved"},
                )
                if response.status_code != 403 or action_count(store, other) != 0:
                    raise AssertionError("A reviewer was able to approve a different case.")
            elif step == "resume":
                try:
                    asyncio.run(client.app.state.service.host.resume(case_id))
                except ActionError:
                    if not action_fails or store.get(case_id).status != "failed":
                        raise
            elif step == "restart":
                client.__exit__(None, None, None)
                client = None
                environment = os.environ.copy()
                environment["MAF_TEST_DATABASE_URL"] = dsn
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "tests.crash_worker",
                        "resume",
                        str(case_id),
                        str(checkpoint_root),
                    ],
                    cwd=BLUEPRINT,
                    env=environment,
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                client = open_client()
            elif step == "simulate_action_failure":
                if not action_fails:
                    raise AssertionError("The action failure was not configured.")
            elif step == "request_hint":
                hint_requested = True
            else:
                raise ValueError(f"Unknown synthetic scenario step: {step}")
        if case_id is None:
            raise ValueError("The fixture did not submit a case.")
        response = client.get(f"/api/cases/{case_id}", headers=headers(owner))
        if response.status_code != 200:
            raise AssertionError(f"Reading the case returned HTTP {response.status_code}.")
        record = response.json()
        payload = record["payload"]
        explanation = (
            f"Case {payload['case_id']} proposes a synthetic adjustment of {payload['amount']} units. "
            f"Adjustments over 100 units require approval. Approval is {record['decision']}. "
            f"Correlation ID: {record['correlation_id']}."
        )
        if record["status"] == "failed":
            explanation += " The configured action failed."
        result = {
            "state": record["status"],
            "action_count": action_count(store, case_id),
            "decision": record["decision"],
            "explanation": explanation,
            "correlation_id": record["correlation_id"],
        }
        if hint_requested:
            result["hint"] = f"Approval is {record['decision']}."
        return result
    finally:
        if client is not None:
            client.__exit__(None, None, None)


if __name__ == "__main__":
    json.dump(run_case(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
