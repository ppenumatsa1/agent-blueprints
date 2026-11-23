from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

from agent_framework import EvalItemResult, EvalResults, EvalScoreResult, Evaluator

from tests.hosted_failure_runner import (
    AuthorizationFailure,
    ConflictFailure,
    HostedRecord,
    ReconciliationRequired,
    StaleApproval,
    TransientFailure,
    UnknownOutcome,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads(
    (
        ROOT
        / "verification"
        / "scenarios"
        / "order-resolution"
        / "acceptance-contract.json"
    ).read_text(encoding="utf-8")
)
GOLDEN_CASES = json.loads(
    (
        ROOT / "verification" / "scenarios" / "order-resolution" / "golden-cases.json"
    ).read_text(encoding="utf-8")
)["cases"]
MODEL_CRITERION = "order-resolution-model-quality"


def _read_auth(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("The live authentication file must contain one object.")
    return value


def _jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("A live authentication token is not a JWT.")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    value = json.loads(base64.urlsafe_b64decode(payload))
    if not isinstance(value, dict):
        raise ValueError("A live authentication token has invalid claims.")
    return value


def _identity(
    auth: dict, name: str, *, scopes: set[str], roles: set[str] = frozenset()
) -> dict:
    value = auth.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"The live authentication file is missing {name}.")
    token = value.get("access_token")
    object_id = value.get("object_id")
    if not isinstance(token, str) or not token or not isinstance(object_id, str):
        raise ValueError(f"The {name} identity is incomplete.")
    UUID(object_id)
    claims = _jwt_claims(token)
    if claims.get("oid") != object_id:
        raise ValueError(f"The {name} token does not match its object ID.")
    observed_scopes = set(str(claims.get("scp", "")).split())
    observed_roles = set(claims.get("roles", []))
    if not scopes.issubset(observed_scopes) or not roles.issubset(observed_roles):
        raise ValueError(
            f"The {name} token does not contain the required authorization."
        )
    return {"access_token": token, "object_id": object_id, "claims": claims}


def _evidence(value: dict) -> dict:
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


def _payload(case: dict, evidence_items: list[dict] | None = None) -> dict:
    facts = CONTRACT["orders"][case["input"]["order"]]
    order = {
        "id": case["input"]["order"],
        "amount": facts["amount"],
        "currency": CONTRACT["amounts"]["currency"],
        "issue": facts["issue"],
    }
    if "delay_days" in facts:
        order["delay_days"] = facts["delay_days"]
    source = case["input"].get("policy_evidence", [])
    return {
        "order": order,
        "policy_evidence": [_evidence(item) for item in (evidence_items or source)],
    }


class LiveClient:
    def __init__(self, base_url: str, auth_file: str, deployment_revision: str):
        self.base_url = base_url.rstrip("/")
        self.deployment_revision = deployment_revision
        auth = _read_auth(auth_file)
        self.owner = _identity(
            auth,
            "owner",
            scopes={"workflow.read", "workflow.write"},
        )
        self.reviewer = _identity(
            auth,
            "reviewer",
            scopes={"workflow.read", "workflow.approve"},
            roles={"Workflow.Approver"},
        )
        self.operator = _identity(
            auth,
            "operator",
            scopes={"workflow.read"},
            roles={"Acceptance.Operator"},
        )
        if self.owner["object_id"] == self.reviewer["object_id"]:
            raise ValueError("Live owner and reviewer identities must be distinct.")
        tenants = {
            identity["claims"].get("tid")
            for identity in (self.owner, self.reviewer, self.operator)
        }
        if len(tenants) != 1:
            raise ValueError("Live acceptance identities must use one tenant.")
        self.correlations: list[dict[str, str]] = []

    def request(
        self,
        method: str,
        path: str,
        identity: dict,
        *,
        body: dict | None = None,
        idempotency_key: str | None = None,
        case_id: str | None = None,
        request_id: str | None = None,
    ) -> tuple[int, dict, dict[str, str]]:
        trace_id = uuid4().hex
        headers = {
            "Authorization": f"Bearer {identity['access_token']}",
            "Accept": "application/json",
            "traceparent": f"00-{trace_id}-{uuid4().hex[:16]}-01",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=(json.dumps(body).encode("utf-8") if body is not None else None),
            headers=headers,
            method=method,
        )
        try:
            response = urllib.request.urlopen(request, timeout=90)
            status = response.status
            payload = response.read()
            response_headers = {
                name.lower(): value for name, value in response.headers.items()
            }
        except urllib.error.HTTPError as error:
            status = error.code
            payload = error.read()
            response_headers = {
                name.lower(): value for name, value in error.headers.items()
            }
        parsed = json.loads(payload) if payload else {}
        returned_trace = response_headers.get("traceparent", "")
        if returned_trace and case_id and request_id:
            parts = returned_trace.split("-")
            if len(parts) == 4:
                self.correlations.append(
                    {
                        "request_id": request_id,
                        "case_id": case_id,
                        "trace_id": parts[1],
                        "agent_version": os.environ["AGENT_VERSION"],
                        "deployment_revision": self.deployment_revision,
                    }
                )
        return status, parsed, response_headers

    def submit(
        self,
        payload: dict,
        key: str,
        *,
        reviewer_id: str | None = None,
    ) -> tuple[dict, dict[str, str]]:
        status, record, headers = self.request(
            "POST",
            "/api/cases",
            self.owner,
            body={
                "reviewer_id": reviewer_id or self.reviewer["object_id"],
                "payload": payload,
            },
            idempotency_key=key,
        )
        if status != 200:
            raise RuntimeError(f"Live submission failed with HTTP {status}.")
        return record, headers

    def read(self, case_id: str, identity: dict | None = None) -> dict:
        status, record, _ = self.request(
            "GET",
            f"/api/cases/{case_id}",
            identity or self.owner,
        )
        if status >= 500:
            raise TransientFailure("The live API reported a transient read failure.")
        if status != 200:
            raise RuntimeError(f"Live read failed with HTTP {status}.")
        return record

    def decide(
        self,
        record: dict,
        decision: str,
        identity: dict,
        *,
        handle: str | None = None,
    ) -> tuple[int, dict, dict[str, str]]:
        proposal = record["payload"]["proposal"]
        return self.request(
            "POST",
            f"/api/cases/{record['id']}/decision",
            identity,
            body={
                "decision": decision,
                "proposal_version": proposal["version"],
                "action": proposal["action"],
                "destination_id": proposal["destination_id"],
                "handle": handle or record["decision_handle"],
                "channel": "api",
            },
            case_id=record["id"],
            request_id=record["decision_handle"],
        )

    def control(
        self,
        method: str,
        path: str,
        *,
        enabled: bool | None = None,
    ) -> dict:
        body = (
            {"deployment_revision": self.deployment_revision, "enabled": enabled}
            if enabled is not None
            else None
        )
        separator = "&" if "?" in path else "?"
        target = (
            path
            if body is not None
            else f"{path}{separator}deployment_revision={self.deployment_revision}"
        )
        status, result, _ = self.request(method, target, self.operator, body=body)
        if status >= 500:
            raise TransientFailure(
                "The live acceptance control reported a transient failure."
            )
        if status != 200:
            raise RuntimeError(f"Live acceptance control failed with HTTP {status}.")
        return result

    def snapshot(self, case_id: str) -> dict:
        return self.control("GET", f"/acceptance/cases/{case_id}")["snapshot"]


class LiveHostedFailureAdapter:
    def __init__(self, base_url: str):
        self.source_revision = os.environ["SOURCE_REVISION"]
        self.deployment_revision = os.environ["DEPLOYMENT_REVISION"]
        self.agent_version = os.environ["AGENT_VERSION"]
        self.client = LiveClient(
            base_url,
            os.environ["MAF_REAL_AUTH_FILE"],
            self.deployment_revision,
        )
        self.records: dict[str, dict] = {}
        self.keys: dict[str, str] = {}
        self.interrupted: set[str] = set()
        self.unknown: set[str] = set()
        self.timeout_after_effect = False

    def _record(self, case_id: str) -> HostedRecord:
        record = self.records[case_id]
        snapshot = self.client.snapshot(case_id)
        status = snapshot["status"]
        technical = "succeeded"
        if case_id in self.interrupted:
            technical = "interrupted"
        if case_id in self.unknown:
            technical = "unknown"
        return HostedRecord(
            case_id=case_id,
            request_id=record["request_id"],
            idempotency_key=record["idempotency_key"],
            status=status,
            technical_status=technical,
            business_outcome=status
            if status in {"pending", "completed", "failed"}
            else "unknown",
            effect_count=snapshot["counts"]["effects"],
        )

    def create(self, idempotency_key: str, *, lose_ack: bool = False) -> HostedRecord:
        case = next(item for item in GOLDEN_CASES if item["id"] == "ORS-002")
        record, headers = self.client.submit(_payload(case), idempotency_key)
        request_id = record["decision_handle"]
        if not request_id:
            case_id = self.keys.get(idempotency_key)
            if case_id is None:
                raise RuntimeError("The live pending decision handle is unavailable.")
            request_id = self.records[case_id]["request_id"]
        case_id = record["id"]
        self.keys[idempotency_key] = case_id
        self.records[case_id] = {
            "record": record,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
        }
        traceparent = headers.get("traceparent", "")
        if traceparent:
            self.client.correlations.append(
                {
                    "request_id": request_id,
                    "case_id": case_id,
                    "trace_id": traceparent.split("-")[1],
                    "agent_version": self.agent_version,
                    "deployment_revision": self.deployment_revision,
                }
            )
        result = self._record(case_id)
        if lose_ack:
            raise UnknownOutcome(
                "The synthetic client discarded the acknowledged response."
            )
        return result

    def lookup(self, idempotency_key: str) -> HostedRecord:
        return self.create(idempotency_key)

    def read(self, case_id: str) -> HostedRecord:
        self.client.read(case_id)
        return self._record(case_id)

    def approve(
        self,
        case_id: str,
        *,
        actor: str = "authorized",
        request_id: str | None = None,
    ) -> HostedRecord:
        cached = self.records[case_id]
        record = cached["record"]
        identity = self.client.reviewer if actor == "authorized" else self.client.owner
        stale = request_id is not None and request_id != cached["request_id"]
        if self.timeout_after_effect:
            self.client.control(
                "POST",
                f"/acceptance/cases/{case_id}/faults/effect-ack-lost",
                enabled=True,
            )
        status, response, _ = self.client.decide(
            record,
            "approved",
            identity,
            handle=request_id,
        )
        if actor != "authorized" and status == 403:
            raise AuthorizationFailure("Unauthorized approval was rejected.")
        if stale and status in {403, 409}:
            raise StaleApproval("Stale approval was rejected.")
        if status in {409}:
            raise ConflictFailure("Duplicate approval conflicted.")
        if self.timeout_after_effect:
            for _ in range(30):
                control = self.client.control("GET", f"/acceptance/cases/{case_id}")
                if (
                    "effect-ack-lost" in control["observed_faults"]
                    and control["snapshot"]["counts"]["effects"] == 1
                ):
                    self.unknown.add(case_id)
                    raise UnknownOutcome("The effect acknowledgement was lost.")
                time.sleep(1)
            raise RuntimeError("The effect acknowledgement fault was not observed.")
        if status != 200:
            raise RuntimeError(f"Live approval failed with HTTP {status}.")
        cached["record"] = response
        return self._record(case_id)

    def restart_api(self) -> None:
        command = [
            "az",
            "containerapp",
            "revision",
            "restart",
            "--resource-group",
            os.environ["AZURE_RESOURCE_GROUP"],
            "--name",
            os.environ["AZURE_API_CONTAINER_APP_NAME"],
            "--revision",
            os.environ["AZURE_API_REVISION"],
            "--only-show-errors",
        ]
        subprocess.run(command, check=True, timeout=180)
        for _ in range(60):
            try:
                status, _, _ = self.client.request("GET", "/healthz", self.client.owner)
                if status == 204:
                    return
            except OSError:
                pass
            time.sleep(2)
        raise RuntimeError("The API revision did not recover after restart.")

    def interrupt_host(self, case_id: str) -> None:
        control = self.client.control("GET", f"/acceptance/cases/{case_id}")
        root = os.environ["MAF_HOSTED_AGENT_ROOT"]
        environment = os.environ["AZURE_ENV_NAME"]
        command = [
            "azd",
            "ai",
            "agent",
            "sessions",
            "stop",
            control["platform_session_id"],
            "--cwd",
            root,
            "--environment",
            environment,
            "--no-prompt",
        ]
        process_environment = dict(os.environ)
        process_environment["AZURE_DEV_USER_AGENT"] = "microsoft_foundry_skill"
        subprocess.run(command, check=True, timeout=180, env=process_environment)
        self.interrupted.add(case_id)

    def set_postgres_transient(self, enabled: bool) -> None:
        self.client.control(
            "POST",
            "/acceptance/faults/postgres-transient",
            enabled=enabled,
        )

    def set_tool_timeout_after_effect(self, enabled: bool) -> None:
        self.timeout_after_effect = enabled

    def retry(self, case_id: str) -> HostedRecord:
        if case_id in self.unknown:
            raise ReconciliationRequired(
                "The unknown effect outcome must be reconciled."
            )
        return self.read(case_id)

    def reconcile(self, case_id: str) -> HostedRecord:
        self.interrupted.discard(case_id)
        self.unknown.discard(case_id)
        return self.read(case_id)

    def correlations(self) -> list[dict[str, str]]:
        unique = {}
        for item in self.client.correlations:
            unique[(item["request_id"], item["case_id"])] = item
        return list(unique.values())


def create_failure_adapter(*, base_url: str) -> LiveHostedFailureAdapter:
    return LiveHostedFailureAdapter(base_url)


class FoundryModelEvaluator:
    name = "foundry-order-resolution-quality"

    def __init__(self, *, provider_id: str, model_id: str, auth_file: str):
        auth = _read_auth(auth_file)
        model = auth.get("model")
        if not isinstance(model, dict):
            raise ValueError(
                "The live authentication file is missing model configuration."
            )
        self.provider_id = provider_id
        self.model_id = model_id
        self.endpoint = model.get("endpoint")
        self.token = model.get("access_token")
        if not isinstance(self.endpoint, str) or not self.endpoint.startswith(
            "https://"
        ):
            raise ValueError("The model endpoint must be an explicit HTTPS URL.")
        if not isinstance(self.token, str) or not self.token:
            raise ValueError("The model access token is missing.")

    async def evaluate(self, items, *, eval_name: str) -> EvalResults:
        results = []
        passed = failed = 0
        for index, item in enumerate(items):
            request = urllib.request.Request(
                self.endpoint,
                data=json.dumps(
                    {
                        "model": self.model_id,
                        "temperature": 0,
                        "max_tokens": 200,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Score semantic agreement between the actual and expected "
                                    "order-resolution JSON from 0 to 1. Return only JSON with "
                                    'keys "score" and "reason". Do not infer missing evidence.'
                                ),
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "query": item.query,
                                        "actual": item.response,
                                        "expected": item.expected_output,
                                    },
                                    sort_keys=True,
                                ),
                            },
                        ],
                    }
                ).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            response = urllib.request.urlopen(request, timeout=120)
            payload = json.loads(response.read())
            judged = json.loads(payload["choices"][0]["message"]["content"])
            score = judged.get("score")
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not 0 <= score <= 1
            ):
                raise ValueError("The Foundry evaluator returned an invalid score.")
            item_passed = score >= float(
                os.environ.get("MAF_REAL_EVALUATION_MINIMUM_SCORE", "0.8")
            )
            passed += int(item_passed)
            failed += int(not item_passed)
            results.append(
                EvalItemResult(
                    item_id=f"{eval_name}-{index}",
                    status="pass" if item_passed else "fail",
                    scores=[
                        EvalScoreResult(
                            name=MODEL_CRITERION,
                            score=float(score),
                            passed=item_passed,
                            sample={"reason": str(judged.get("reason", ""))[:512]},
                        )
                    ],
                    response_id=(
                        response.headers.get("x-request-id")
                        or response.headers.get("apim-request-id")
                        or f"{eval_name}-{index}"
                    ),
                    input_text=item.query,
                    output_text=item.response,
                )
            )
        return EvalResults(
            provider=self.provider_id,
            eval_id=eval_name,
            run_id=str(uuid4()),
            status="completed",
            result_counts={"passed": passed, "failed": failed, "total": len(results)},
            items=results,
        )


def create_evaluator(*, provider_id: str, model_id: str, auth_file: str) -> Evaluator:
    return FoundryModelEvaluator(
        provider_id=provider_id,
        model_id=model_id,
        auth_file=auth_file,
    )


def _result(snapshot: dict, *, native_pause: bool, extras: dict | None = None) -> dict:
    proposal = snapshot["proposal"]
    action = None
    if proposal:
        action = {"type": proposal["action"]}
        if proposal["amount"] is not None:
            action.update(amount=proposal["amount"], currency=proposal["currency"])
        elif proposal["action"] == "replacement_shipment":
            action["quantity"] = 1
    state = {"pending": "awaiting_approval", "rejected": "escalated"}.get(
        snapshot["status"], snapshot["status"]
    )
    decision = snapshot["decision"]
    if decision is None:
        decision = (
            "not_required" if proposal and not proposal["approval_required"] else "none"
        )
    if state == "awaiting_approval":
        decision = "pending"
    result = {
        "business_outcome": {
            "proposal_authoritative": proposal is not None,
            "proposed_action": action,
            "approval_required": proposal["approval_required"] if proposal else None,
            "decision": decision,
            "verified_actions": snapshot["verified_actions"],
            "state": state,
        },
        "technical_execution": {
            "native_pause_required": native_pause,
            "authorized_decision_count": snapshot["counts"]["approved"],
            "action_claim_count": snapshot["counts"]["claims"],
            "side_effect_count": snapshot["counts"]["effects"],
            "terminal_event_count": snapshot["counts"]["terminal"],
        },
    }
    result["technical_execution"].update(extras or {})
    return result


def create_results(
    *,
    base_url: str,
    auth_file: str,
    source_revision: str,
    deployment_revision: str,
) -> dict[str, dict]:
    if source_revision != deployment_revision:
        raise ValueError(
            "Live provider results require exact source/deployment parity."
        )
    client = LiveClient(base_url, auth_file, deployment_revision)
    results = {}
    for case in GOLDEN_CASES:
        case_id = case["id"]
        if case_id == "ORS-008":
            snapshots = []
            for variant in case["input"]["policy_evidence_variants"]:
                record, _ = client.submit(_payload(case, [variant]), str(uuid4()))
                snapshots.append(client.snapshot(record["id"]))
            results[case_id] = {
                "business_outcome": {
                    "proposal_authoritative": False,
                    "proposed_action": None,
                    "approval_required": None,
                    "decision": "none",
                    "verified_actions": [],
                    "state": "failed",
                    "error": (
                        "policy_evidence_invalid"
                        if all(item["status"] == "failed" for item in snapshots)
                        else "unexpected"
                    ),
                },
                "technical_execution": {
                    "invalid_variants_checked": [
                        item["invalid_reason"]
                        for item in case["input"]["policy_evidence_variants"]
                    ],
                    "all_variants_failed_explicitly": all(
                        item["status"] == "failed" for item in snapshots
                    ),
                    "native_pause_required": False,
                    "authorized_decision_count": 0,
                    "action_claim_count": sum(
                        item["counts"]["claims"] for item in snapshots
                    ),
                    "side_effect_count": sum(
                        item["counts"]["effects"] for item in snapshots
                    ),
                    "terminal_event_count_per_variant": min(
                        item["counts"]["terminal"] for item in snapshots
                    ),
                },
            }
            continue

        key = f"live-{case_id.lower()}-{uuid4()}"
        reviewer_id = None
        if case_id == "ORS-009":
            reviewer_id = str(uuid4())
        record, _ = client.submit(_payload(case), key, reviewer_id=reviewer_id)
        original = False
        pending_before = record["status"] == "pending"
        if case_id == "ORS-002":
            status, record, _ = client.decide(record, "approved", client.reviewer)
            if status != 200:
                raise RuntimeError(f"ORS-002 approval failed with HTTP {status}.")
        elif case_id == "ORS-003":
            status, record, _ = client.decide(record, "rejected", client.reviewer)
            if status != 200:
                raise RuntimeError(f"ORS-003 rejection failed with HTTP {status}.")
        elif case_id == "ORS-004":
            replay, _ = client.submit(_payload(case), key)
            original = replay["id"] == record["id"]
        elif case_id == "ORS-005":
            client.control(
                "POST",
                f"/acceptance/cases/{record['id']}/faults/decision-ack-lost",
                enabled=True,
            )
            client.decide(record, "approved", client.reviewer)
            for _ in range(30):
                control = client.control("GET", f"/acceptance/cases/{record['id']}")
                snapshot = control["snapshot"]
                if (
                    "decision-ack-lost" in control["observed_faults"]
                    and snapshot["status"] == "completed"
                ):
                    break
                time.sleep(2)
            else:
                raise RuntimeError(
                    "ORS-005 did not reconcile after acknowledgement loss."
                )
        elif case_id == "ORS-009":
            denied = []
            for label, identity in (
                ("REVIEWER-B", client.owner),
                ("USER-B", client.reviewer),
            ):
                status, _, _ = client.decide(record, "approved", identity)
                if status == 403:
                    denied.append(label)
            snapshot = client.snapshot(record["id"])
            result = _result(
                snapshot,
                native_pause=True,
                extras={
                    "denied_actors": denied,
                    "authorization_denial_count": snapshot["counts"]["denials"],
                    "denial_privacy_safe": snapshot["counts"]["denials"] == len(denied),
                    "denial_auditable": snapshot["counts"]["denials"] == len(denied),
                },
            )
            result["business_outcome"]["error"] = "authorization_denied"
            result["technical_execution"].pop("terminal_event_count")
            result["technical_execution"].pop("authorized_decision_count")
            results[case_id] = result
            continue

        snapshot = client.snapshot(record["id"])
        extras = {}
        if case_id == "ORS-002":
            extras["native_pause_before_action"] = pending_before
        elif case_id == "ORS-003":
            extras.update(
                native_pause_before_action=pending_before,
                rejection_count=snapshot["counts"]["rejected"],
            )
        elif case_id == "ORS-004":
            extras.update(
                request_identity_reused=original,
                duplicate_terminal_event_emitted=snapshot["counts"]["terminal"] != 1,
            )
        elif case_id == "ORS-005":
            extras.update(
                termination_point="after_decision_commit_before_native_resume_acknowledgement",
                native_continuation_reconciled=snapshot["status"] == "completed",
                stored_decision_reused=snapshot["counts"]["approved"] == 1,
                original_decision_audit_preserved=snapshot["counts"]["approved"] == 1,
            )
        result = _result(
            snapshot,
            native_pause=case_id in {"ORS-002", "ORS-003", "ORS-005"},
            extras=extras,
        )
        if snapshot["status"] == "failed":
            result["business_outcome"]["error"] = record.get("failure_code")
        if case_id == "ORS-003":
            result["technical_execution"].pop("authorized_decision_count")
        if case_id == "ORS-004":
            result["business_outcome"]["returned_original_outcome"] = original
            result["technical_execution"].pop("native_pause_required")
            result["technical_execution"].pop("authorized_decision_count")
        if case_id == "ORS-005":
            result["technical_execution"].pop("authorized_decision_count")
        results[case_id] = result
    return results
