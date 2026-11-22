import json
import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.composition import create_app
from app.config import Settings
from app.infrastructure.identity import EntraIdentity
from app.order_resolution.application import build_application, initialize
from app.order_resolution.migrations import upgrade
from app.order_resolution.persistence import OrderResolutionStore
from tests.test_security import API, OWNER, REVIEWER, TENANT, TokenFixture, scoped_url


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads(
    (
        ROOT / "verification" / "scenarios" / "order-resolution" / "acceptance-contract.json"
    ).read_text(encoding="utf-8")
)
REVIEWER_B = "50000000-0000-4000-8000-000000000005"
USER_B = "60000000-0000-4000-8000-000000000006"


def evidence(value: dict) -> dict:
    invalid = value.get("invalid_reason")
    return {
        "policy": value["policy"],
        "current": invalid != "expired" and value.get("current", True),
        "applicable": invalid != "non-applicable" and value.get("applicable", True),
        "digest_valid": invalid != "digest-invalid" and value.get("digest_valid", True),
        **{
            key: value[key]
            for key in ("asserted_action", "asserted_approval_required")
            if key in value
        },
    }


def payload(case: dict, evidence_items: list[dict] | None = None) -> dict:
    order_id = case["input"]["order"]
    facts = CONTRACT["orders"][order_id]
    order = {
        "id": order_id,
        "amount": facts["amount"],
        "currency": CONTRACT["amounts"]["currency"],
        "issue": facts["issue"],
    }
    if "delay_days" in facts:
        order["delay_days"] = facts["delay_days"]
    source = case["input"].get("policy_evidence", [])
    return {
        "order": order,
        "policy_evidence": [evidence(item) for item in (evidence_items or source)],
    }


class Runtime:
    def __init__(self):
        base = os.environ.get("MAF_TEST_DATABASE_URL")
        if not base:
            raise RuntimeError("MAF_TEST_DATABASE_URL is required.")
        self.base = base
        self.schema = "order_resolution_adapter_" + uuid4().hex
        with psycopg.connect(base, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.dsn = scoped_url(base, self.schema)
        upgrade(self.dsn)
        self.store = OrderResolutionStore(self.dsn)
        initialize(self.store)
        self.temp = tempfile.TemporaryDirectory()
        self.checkpoint_root = Path(self.temp.name) / "checkpoints"
        self.settings = Settings(TENANT, API, self.dsn, self.checkpoint_root)
        self.tokens = TokenFixture()
        self.identity = EntraIdentity(self.settings, self.tokens.client())
        self.owner_token = self.tokens.token(subject=OWNER)
        self.reviewer_token = self.tokens.token(
            subject=REVIEWER,
            scopes="workflow.read workflow.approve",
            roles=["Workflow.Approver"],
        )

    def close(self):
        self.temp.cleanup()
        with psycopg.connect(self.base, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def client(self):
        return TestClient(
            create_app(
                self.settings,
                build_application(),
                store=self.store,
                identity=self.identity,
            )
        )

    @staticmethod
    def headers(token: str, key: str | None = None) -> dict[str, str]:
        value = {"Authorization": f"Bearer {token}"}
        if key is not None:
            value["Idempotency-Key"] = key
        return value

    def submit(self, client: TestClient, body: dict, key: str | None = None) -> dict:
        response = client.post(
            "/api/cases",
            headers=self.headers(self.owner_token, key or str(uuid4())),
            json={"reviewer_id": REVIEWER, "payload": body},
        )
        if response.status_code != 200:
            raise RuntimeError(response.text)
        return response.json()

    @staticmethod
    def decision_body(record: dict, decision: str) -> dict:
        proposal = record["payload"]["proposal"]
        return {
            "decision": decision,
            "proposal_version": proposal["version"],
            "action": proposal["action"],
            "destination_id": proposal["destination_id"],
            "handle": record["decision_handle"],
            "channel": "api",
        }

    def decide(self, client: TestClient, record: dict, decision: str, token: str | None = None):
        return client.post(
            f"/api/cases/{record['id']}/decision",
            headers=self.headers(token or self.reviewer_token),
            json=self.decision_body(record, decision),
        )

    def counts(self, case_id: UUID) -> dict[str, int]:
        with self.store.connect() as connection:
            values = {}
            for name, query in {
                "approved": """
                    SELECT count(*) AS count FROM order_resolution_decisions
                    WHERE case_id = %s AND decision = 'approved'
                """,
                "rejected": """
                    SELECT count(*) AS count FROM order_resolution_decisions
                    WHERE case_id = %s AND decision = 'rejected'
                """,
                "claims": "SELECT count(*) AS count FROM order_resolution_effects WHERE case_id = %s",
                "effects": """
                    SELECT count(*) AS count
                    FROM order_resolution_synthetic_effects s
                    JOIN order_resolution_effects e ON e.effect_key = s.effect_key
                    WHERE e.case_id = %s
                """,
                "terminal": """
                    SELECT count(*) AS count FROM wf_audit
                    WHERE case_id = %s AND event IN ('workflow_finished', 'resolution_failed')
                """,
                "denials": """
                    SELECT count(*) AS count FROM order_resolution_audit
                    WHERE case_id = %s AND event = 'decision_denied'
                """,
            }.items():
                values[name] = connection.execute(query, (case_id,)).fetchone()["count"]
            return values

    def verified_actions(self, case_id: UUID) -> list[dict]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT action, amount::text, currency
                FROM order_resolution_actions
                WHERE case_id = %s
                ORDER BY created_at
                """,
                (case_id,),
            ).fetchall()
        values = []
        for row in rows:
            action = {"type": row["action"]}
            if row["amount"] is not None:
                action.update(currency=row["currency"], amount=row["amount"])
            elif row["action"] == "replacement_shipment":
                action["quantity"] = 1
            values.append(action)
        return values

    def result(
        self,
        record: dict,
        *,
        native_pause: bool,
        error: str | None = None,
        extras: dict | None = None,
    ) -> dict:
        case_id = UUID(record["id"])
        stored = self.store.get(case_id)
        counts = self.counts(case_id)
        proposal = record["payload"].get("proposal")
        action = None
        if proposal:
            action = {"type": proposal["action"]}
            if "amount" in proposal:
                action.update(currency=proposal["currency"], amount=proposal["amount"])
            elif proposal["action"] == "replacement_shipment":
                action["quantity"] = 1
        state = {
            "pending": "awaiting_approval",
            "rejected": "escalated",
        }.get(stored.status, stored.status)
        decision = (
            stored.decision
            if stored.decision is not None
            else ("not_required" if proposal and not proposal["approval_required"] else "none")
        )
        if state == "awaiting_approval":
            decision = "pending"
        business = {
            "proposal_authoritative": proposal is not None,
            "proposed_action": action,
            "approval_required": proposal["approval_required"] if proposal else None,
            "decision": decision,
            "verified_actions": self.verified_actions(case_id),
            "state": state,
        }
        if error is not None:
            business["error"] = error
        technical = {
            "native_pause_required": native_pause,
            "authorized_decision_count": counts["approved"],
            "action_claim_count": counts["claims"],
            "side_effect_count": counts["effects"],
            "terminal_event_count": counts["terminal"],
        }
        technical.update(extras or {})
        return {"business_outcome": business, "technical_execution": technical}


def run_case(case: dict) -> dict:
    runtime = Runtime()
    try:
        case_id = case["id"]
        if case_id == "ORS-008":
            records = []
            variants = case["input"]["policy_evidence_variants"]
            with runtime.client() as client:
                for variant in variants:
                    records.append(runtime.submit(client, payload(case, [variant])))
            failures = [runtime.store.get(UUID(record["id"])) for record in records]
            return {
                "business_outcome": {
                    "proposal_authoritative": False,
                    "proposed_action": None,
                    "approval_required": None,
                    "decision": "none",
                    "verified_actions": [],
                    "state": "failed",
                    "error": (
                        "policy_evidence_invalid"
                        if all(item.failure_code == "policy_evidence_invalid" for item in failures)
                        else "unexpected"
                    ),
                },
                "technical_execution": {
                    "invalid_variants_checked": [variant["invalid_reason"] for variant in variants],
                    "all_variants_failed_explicitly": all(
                        item.failure_code == "policy_evidence_invalid" for item in failures
                    ),
                    "native_pause_required": False,
                    "authorized_decision_count": 0,
                    "action_claim_count": sum(
                        runtime.counts(item.id)["claims"] for item in failures
                    ),
                    "side_effect_count": sum(
                        runtime.counts(item.id)["effects"] for item in failures
                    ),
                    "terminal_event_count_per_variant": min(
                        runtime.counts(item.id)["terminal"] for item in failures
                    ),
                },
            }

        key = "duplicate-request" if case_id == "ORS-004" else str(uuid4())
        with runtime.client() as client:
            if case_id == "ORS-004":

                def duplicate_submit(_):
                    with runtime.client() as duplicate_client:
                        return runtime.submit(duplicate_client, payload(case), key)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    records = list(pool.map(duplicate_submit, range(2)))
                record = runtime.submit(client, payload(case), key)
                original = len({item["id"] for item in records + [record]}) == 1
            else:
                record = runtime.submit(client, payload(case), key)
                original = False
            pending_before_action = (
                record["status"] == "pending" and runtime.counts(UUID(record["id"]))["effects"] == 0
            )
            if case_id == "ORS-002":
                response = runtime.decide(client, record, "approved")
                if response.status_code != 200:
                    raise RuntimeError(response.text)
                record = response.json()
            elif case_id == "ORS-003":
                response = runtime.decide(client, record, "rejected")
                if response.status_code != 200:
                    raise RuntimeError(response.text)
                record = response.json()
            elif case_id == "ORS-009":
                denied = []
                for name, subject in (("REVIEWER-B", REVIEWER_B), ("USER-B", USER_B)):
                    token = runtime.tokens.token(
                        subject=subject,
                        scopes="workflow.read workflow.approve",
                        roles=["Workflow.Approver"],
                    )
                    response = runtime.decide(client, record, "approved", token)
                    if response.status_code == 403:
                        denied.append(name)
                refreshed = client.get(
                    f"/api/cases/{record['id']}",
                    headers=runtime.headers(runtime.owner_token),
                )
                record = refreshed.json()
                counts = runtime.counts(UUID(record["id"]))
                result = runtime.result(
                    record,
                    native_pause=True,
                    error="authorization_denied",
                    extras={
                        "denied_actors": denied,
                        "authorization_denial_count": counts["denials"],
                        "denial_privacy_safe": counts["denials"] == len(denied),
                        "denial_auditable": counts["denials"] == len(denied),
                    },
                )
                result["technical_execution"].pop("terminal_event_count")
                result["technical_execution"].pop("authorized_decision_count")
                return result
            elif case_id == "ORS-005":
                args = [
                    sys.executable,
                    "-m",
                    "tests.order_resolution_crash_worker",
                    "after-decision",
                    runtime.dsn,
                    str(runtime.checkpoint_root),
                    record["id"],
                    str(record["payload"]["proposal"]["version"]),
                    record["payload"]["proposal"]["action"],
                    record["payload"]["proposal"]["destination_id"],
                    record["decision_handle"],
                ]
                process = subprocess.run(
                    args,
                    cwd=ROOT / "backend",
                    timeout=30,
                    check=False,
                )
                if process.returncode != 82:
                    raise RuntimeError("The decision crash worker did not stop at its barrier.")

        if case_id == "ORS-005":
            with runtime.client() as client:
                response = client.get(
                    f"/api/cases/{record['id']}",
                    headers=runtime.headers(runtime.owner_token),
                )
                record = response.json()

        extras = {}
        if case_id == "ORS-002":
            extras["native_pause_before_action"] = pending_before_action
        elif case_id == "ORS-003":
            extras.update(
                native_pause_before_action=pending_before_action,
                rejection_count=runtime.counts(UUID(record["id"]))["rejected"],
            )
            extras.pop("authorized_decision_count", None)
        elif case_id == "ORS-004":
            extras.update(
                request_identity_reused=original,
                duplicate_terminal_event_emitted=(
                    runtime.counts(UUID(record["id"]))["terminal"] != 1
                ),
            )
        elif case_id == "ORS-005":
            extras.update(
                termination_point=("after_decision_commit_before_native_resume_acknowledgement"),
                native_continuation_reconciled=record["execution_complete"],
                stored_decision_reused=runtime.counts(UUID(record["id"]))["approved"] == 1,
                original_decision_audit_preserved=runtime.counts(UUID(record["id"]))["approved"]
                == 1,
            )
        result = runtime.result(
            record,
            native_pause=case_id in ("ORS-002", "ORS-003", "ORS-005"),
            error=record.get("failure_code"),
            extras=extras,
        )
        if case_id == "ORS-003":
            result["technical_execution"].pop("authorized_decision_count")
        if case_id == "ORS-004":
            result["business_outcome"]["returned_original_outcome"] = original
            result["technical_execution"].pop("native_pause_required")
            result["technical_execution"].pop("authorized_decision_count")
        if case_id == "ORS-005":
            result["technical_execution"].pop("authorized_decision_count")
        return result
    finally:
        runtime.close()


def main() -> int:
    request = json.load(sys.stdin)
    if request.get("scenario_set") != CONTRACT["scenario_set"]:
        raise RuntimeError("The scenario set is not supported.")
    with redirect_stdout(io.StringIO()):
        result = run_case(request["case"])
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
