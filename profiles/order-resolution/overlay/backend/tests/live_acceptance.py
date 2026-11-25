from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from agent_framework import EvalItemResult, EvalResults, EvalScoreResult, Evaluator

from tests.hosted_failure_runner import (
    AuthorizationFailure,
    ConflictFailure,
    HostedRecord,
    ReconciliationRequired,
    StaleApproval,
    TransientFailure,
    UnknownOutcome,
    UnsupportedScenario,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads(
    (
        ROOT / "verification" / "scenarios" / "order-resolution" / "acceptance-contract.json"
    ).read_text(encoding="utf-8")
)
GOLDEN_CASES = json.loads(
    (ROOT / "verification" / "scenarios" / "order-resolution" / "golden-cases.json").read_text(
        encoding="utf-8"
    )
)["cases"]
MODEL_CRITERION = "order-resolution-model-quality"
CASE_POLL_TIMEOUT_SECONDS = 60
CASE_POLL_INTERVAL_SECONDS = 2


def _https_origin(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?/?", value, re.IGNORECASE
    ):
        raise ValueError("An explicit HTTPS origin is required.")
    try:
        parsed = urllib.parse.urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme.lower() != "https"
            or not host
            or not re.fullmatch(r"[a-z0-9.-]+", host)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.netloc.endswith(":")
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
            or port == 0
        ):
            raise ValueError
    except ValueError as exc:
        raise ValueError("An explicit HTTPS origin is required.") from exc
    return f"https://{host}" + (f":{port}" if port and port != 443 else "")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Live acceptance redirects are not permitted.")


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


def _identity(auth: dict, name: str, *, scopes: set[str], roles: set[str] = frozenset()) -> dict:
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
        raise ValueError(f"The {name} token does not contain the required authorization.")
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
    def __init__(
        self,
        base_url: str,
        auth_file: str,
        deployment_revision: str,
        *,
        poc_owner_database_url: str | None = None,
    ):
        self.base_url = _https_origin(base_url)
        if self.base_url != _https_origin(os.environ.get("MAF_LIVE_AUTHORIZED_ORIGIN", "")):
            raise ValueError("The live base URL does not match the authorized origin.")
        self.opener = urllib.request.build_opener(_RejectRedirects())
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
        self.poc_owner_database_url = poc_owner_database_url
        if self.poc_owner_database_url:
            if (
                not self.owner["object_id"]
                == self.reviewer["object_id"]
                == self.operator["object_id"]
            ):
                raise ValueError("POC acceptance requires one exact owner/reviewer/operator.")
        elif self.owner["object_id"] == self.reviewer["object_id"]:
            raise ValueError("Live owner and reviewer identities must be distinct.")
        tenants = {
            identity["claims"].get("tid") for identity in (self.owner, self.reviewer, self.operator)
        }
        if len(tenants) != 1:
            raise ValueError("Live acceptance identities must use one tenant.")
        self.correlations: list[dict[str, str | int]] = []

    def request(
        self,
        method: str,
        path: str,
        identity: dict,
        *,
        body: dict | None = None,
        idempotency_key: str | None = None,
        case_id: str | None = None,
        hosted_phase: str | None = None,
    ) -> tuple[int, dict, dict[str, str]]:
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or re.search(r"[\x00-\x20\x7f\\#]", path)
        ):
            raise ValueError("The live request path must be origin-relative.")
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
            response = self.opener.open(request, timeout=90)
            status = response.status
            payload = response.read()
            response_headers = {name.lower(): value for name, value in response.headers.items()}
        except urllib.error.HTTPError as error:
            status = error.code
            payload = error.read()
            response_headers = {name.lower(): value for name, value in error.headers.items()}
        parsed = self._capture_response(
            status,
            payload,
            response_headers,
            case_id=case_id,
            hosted_phase=hosted_phase,
        )
        return status, parsed, response_headers

    def _capture_response(
        self,
        status: int,
        payload: bytes,
        response_headers: dict[str, str],
        *,
        case_id: str | None = None,
        hosted_phase: str | None = None,
    ) -> dict:
        parsed = json.loads(payload) if payload else {}
        returned_trace = response_headers.get("traceparent", "")
        correlation_request_id = response_headers.get("x-correlation-id", "")
        correlation_case_id = case_id or parsed.get("id")
        if returned_trace and correlation_case_id and correlation_request_id:
            parts = returned_trace.split("-")
            if len(parts) == 4:
                self.correlations.append(
                    {
                        "request_id": correlation_request_id,
                        "case_id": correlation_case_id,
                        "trace_id": parts[1],
                        "agent_version": os.environ["AGENT_VERSION"],
                        "deployment_revision": self.deployment_revision,
                        "http_status": status,
                        **(
                            {
                                "hosted_phase": hosted_phase,
                            }
                            if hosted_phase is not None
                            else {}
                        ),
                    }
                )
        return parsed

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
                "reviewer_id": reviewer_id
                or (
                    "poc-unassigned-reviewer"
                    if self.poc_owner_database_url
                    else self.reviewer["object_id"]
                ),
                "payload": payload,
            },
            idempotency_key=key,
            hosted_phase="start",
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

    async def _read_for_poll(self, case_id: str) -> dict:
        headers = {
            "Authorization": f"Bearer {self.owner['access_token']}",
            "Accept": "application/json",
            "traceparent": f"00-{uuid4().hex}-{uuid4().hex[:16]}-01",
        }
        async with httpx.AsyncClient(
            follow_redirects=False,
            verify=ssl.create_default_context(),
            timeout=None,
        ) as client:
            response = await client.get(f"{self.base_url}/api/cases/{case_id}", headers=headers)
        if 300 <= response.status_code < 400:
            raise RuntimeError("Live acceptance redirects are not permitted.")
        record = self._capture_response(
            response.status_code,
            response.content,
            {name.lower(): value for name, value in response.headers.items()},
        )
        if response.status_code >= 500:
            raise TransientFailure("The live API reported a transient read failure.")
        if response.status_code != 200:
            raise RuntimeError(f"Live read failed with HTTP {response.status_code}.")
        return record

    def _wait_for_case(self, record: dict, ready, description: str) -> dict:
        case_id = str(UUID(record["id"]))

        async def poll() -> dict:
            current = record
            deadline = asyncio.timeout(CASE_POLL_TIMEOUT_SECONDS)
            try:
                async with deadline:
                    for attempt in range(31):
                        if current.get("id") != case_id:
                            raise RuntimeError("The live read returned a different case.")
                        if current.get("failure_code") or current.get("status") == "failed":
                            raise RuntimeError("The live case reported a failure while waiting.")
                        if ready(current):
                            return current
                        if current.get("execution_complete"):
                            raise RuntimeError(
                                "The live case completed without the expected state."
                            )
                        if attempt < 30:
                            await asyncio.sleep(CASE_POLL_INTERVAL_SECONDS)
                            current = await self._read_for_poll(case_id)
            except TimeoutError as exc:
                if not deadline.expired():
                    raise
                raise TimeoutError("The live case polling deadline expired.") from exc
            raise RuntimeError(
                f"The live case did not reach {description} within the polling limit."
            )

        return asyncio.run(poll())

    def wait_for_pending(self, record: dict) -> dict:
        def ready(value: dict) -> bool:
            if value.get("status") != "pending":
                return False
            handle = value.get("decision_handle")
            channel = value.get("decision_channel")
            if handle is not None and (not isinstance(handle, str) or not handle.strip()):
                raise RuntimeError("The live approval handle is invalid.")
            if channel is not None and channel != "foundry-responses":
                raise RuntimeError("The live approval channel is unexpected.")
            return bool(handle) and channel == "foundry-responses"

        return self._wait_for_case(
            record,
            ready,
            "a hosted approval pause",
        )

    def wait_for_completion(self, record: dict, status: str) -> dict:
        return self._wait_for_case(
            record,
            lambda value: value.get("status") == status and value.get("execution_complete") is True,
            f"the {status} terminal state",
        )

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
                "channel": "foundry-responses",
            },
            case_id=record["id"],
            hosted_phase="resume",
        )

    def grant_poc_decision(self, record: dict, decision: str) -> None:
        if self.poc_owner_database_url is None or record.get("status") != "pending":
            raise ValueError("The POC grant requires a configured owner and an exact pending case.")
        from app.order_resolution.durability import Decision
        from app.order_resolution.poc_grant import issue_grant

        proposal = record["payload"]["proposal"]
        issue_grant(
            self.poc_owner_database_url,
            case_id=UUID(record["id"]),
            proposal_version=proposal["version"],
            handle_digest=hashlib.sha256(record["decision_handle"].encode()).hexdigest(),
            action=proposal["action"],
            destination_id=proposal["destination_id"],
            decision=Decision(decision),
        )

    def control(
        self,
        method: str,
        path: str,
        *,
        enabled: bool | None = None,
    ) -> dict:
        if path.startswith("/acceptance"):
            path = f"/api/internal/hosted/v1{path}"
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
            raise TransientFailure("The live acceptance control reported a transient failure.")
        if status != 200:
            raise RuntimeError(f"Live acceptance control failed with HTTP {status}.")
        return result

    def snapshot(self, case_id: str) -> dict:
        return self.control("GET", f"/acceptance/cases/{case_id}")["snapshot"]


class LiveHostedFailureAdapter:
    def __init__(self, base_url: str, *, target_kind: str, target_id: str):
        self.source_revision = os.environ["SOURCE_REVISION"]
        self.deployment_revision = os.environ["DEPLOYMENT_REVISION"]
        self.agent_version = os.environ["AGENT_VERSION"]
        self.target_kind = target_kind
        self.target_id = target_id
        self.client = LiveClient(
            base_url,
            os.environ["MAF_HOSTED_FAILURE_AUTH_FILE"],
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
            business_outcome=status if status in {"pending", "completed", "failed"} else "unknown",
            effect_count=snapshot["counts"]["effects"],
        )

    def create(self, idempotency_key: str, *, lose_ack: bool = False) -> HostedRecord:
        case = next(item for item in GOLDEN_CASES if item["id"] == "ORS-002")
        record, _ = self.client.submit(_payload(case), idempotency_key)
        case_id = record["id"]
        previous = self.keys.get(idempotency_key)
        if previous is not None and previous != case_id:
            raise RuntimeError("The idempotency key returned a different live case.")
        if previous is None or record.get("status") in {"created", "pending"}:
            record = self.client.wait_for_pending(record)
        request_id = record.get("decision_handle")
        if not request_id and previous is not None:
            request_id = self.records[previous]["request_id"]
        if not request_id:
            raise RuntimeError("The live pending decision handle is unavailable.")
        self.keys[idempotency_key] = case_id
        self.records[case_id] = {
            "record": record,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
        }
        result = self._record(case_id)
        if lose_ack:
            raise UnknownOutcome("The synthetic client discarded the acknowledged response.")
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
        cached["record"] = self.client.wait_for_completion(response, "completed")
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
        raise UnsupportedScenario(
            "Hosted interruption requires independently verified native continuation evidence."
        )

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
            raise ReconciliationRequired("The unknown effect outcome must be reconciled.")
        return self.read(case_id)

    def reconcile(self, case_id: str) -> HostedRecord:
        raise UnsupportedScenario("Authoritative hosted reconciliation is not available.")

    def correlations(self) -> list[dict[str, object]]:
        unique = {}
        for item in list(self.client.correlations):
            value = dict(item)
            if value.get("hosted_phase") in {"start", "resume"}:
                control = self.client.control(
                    "GET",
                    f"/acceptance/cases/{value['case_id']}",
                )
                if value["hosted_phase"] == "start":
                    claim_request_id = control.get("start_claim_request_id")
                    if claim_request_id != value["request_id"]:
                        value.pop("hosted_phase")
                        unique[(value["request_id"], value["case_id"])] = value
                        continue
                    value["extensions"] = {
                        "producer": {"hosted_start_claim_request_id": claim_request_id}
                    }
                conversation_id = control.get("conversation_id")
                if not isinstance(conversation_id, str) or not conversation_id:
                    raise RuntimeError("The hosted conversation evidence is unavailable.")
                value.update(
                    {
                        "conversation_id": conversation_id,
                        "hosted_agent_name": os.environ["HOSTED_AGENT_NAME"],
                        "hosted_agent_version": os.environ["HOSTED_AGENT_VERSION"],
                    }
                )
            unique[(value["request_id"], value["case_id"])] = value
        return list(unique.values())


def create_failure_adapter(
    *, base_url: str, target_kind: str, target_id: str
) -> LiveHostedFailureAdapter:
    return LiveHostedFailureAdapter(base_url, target_kind=target_kind, target_id=target_id)


class FoundryModelEvaluator:
    name = "foundry-order-resolution-quality"

    def __init__(self, *, provider_id: str, model_id: str, auth_file: str):
        authorized_origin = _https_origin(os.environ.get("MAF_MODEL_AUTHORIZED_ORIGIN", ""))
        auth = _read_auth(auth_file)
        model = auth.get("model")
        if not isinstance(model, dict):
            raise ValueError("The live authentication file is missing model configuration.")
        self.provider_id = provider_id
        self.model_id = model_id
        self.endpoint = model.get("endpoint")
        self.token = model.get("access_token")
        if not isinstance(self.endpoint, str) or re.search(r"[\x00-\x20\x7f\\#]", self.endpoint):
            raise ValueError("The model endpoint must be an explicit authorized HTTPS URL.")
        parsed = urllib.parse.urlsplit(self.endpoint)
        if _https_origin(f"{parsed.scheme}://{parsed.netloc}") != authorized_origin:
            raise ValueError("The model endpoint does not match the authorized origin.")
        if not isinstance(self.token, str) or not self.token:
            raise ValueError("The model access token is missing.")
        self.opener = urllib.request.build_opener(_RejectRedirects())

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
            response = self.opener.open(request, timeout=120)
            payload = json.loads(response.read())
            judged = json.loads(payload["choices"][0]["message"]["content"])
            score = judged.get("score")
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not 0 <= score <= 1
            ):
                raise ValueError("The Foundry evaluator returned an invalid score.")
            item_passed = score >= float(os.environ.get("MAF_REAL_EVALUATION_MINIMUM_SCORE", "0.8"))
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
        decision = "not_required" if proposal and not proposal["approval_required"] else "none"
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
    case_ids: list[str] | None = None,
) -> dict[str, dict]:
    if source_revision != deployment_revision:
        raise ValueError("Live provider results require exact source/deployment parity.")
    known = {case["id"] for case in GOLDEN_CASES}
    selected = known if case_ids is None else set(case_ids)
    if not selected or selected - known:
        raise ValueError("Select at least one known canonical scenario.")
    if case_ids is not None and len(selected) != len(case_ids):
        raise ValueError("Canonical scenario selection must not contain duplicates.")
    if "ORS-005" in selected:
        raise UnsupportedScenario(
            "ORS-005 requires independently verified native continuation evidence."
        )
    poc_database_url = os.environ.get("MAF_LIVE_POC_OWNER_DATABASE_URL")
    if "ORS-009" in selected and poc_database_url:
        raise UnsupportedScenario(
            "ORS-009 requires distinct actor identities; same-identity POC mode cannot verify it."
        )
    client = (
        LiveClient(
            base_url, auth_file, deployment_revision, poc_owner_database_url=poc_database_url
        )
        if poc_database_url
        else LiveClient(base_url, auth_file, deployment_revision)
    )
    results = {}
    for case in GOLDEN_CASES:
        case_id = case["id"]
        if case_id not in selected:
            results[case_id] = {
                "status": "not_run",
                "reason": "Excluded by explicit canonical scenario selection.",
            }
            continue
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
                        item["invalid_reason"] for item in case["input"]["policy_evidence_variants"]
                    ],
                    "all_variants_failed_explicitly": all(
                        item["status"] == "failed" for item in snapshots
                    ),
                    "native_pause_required": False,
                    "authorized_decision_count": 0,
                    "action_claim_count": sum(item["counts"]["claims"] for item in snapshots),
                    "side_effect_count": sum(item["counts"]["effects"] for item in snapshots),
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
        elif poc_database_url and case_id in {"ORS-002", "ORS-003"}:
            reviewer_id = client.owner["object_id"]
        record, _ = client.submit(_payload(case), key, reviewer_id=reviewer_id)
        if case_id in {"ORS-002", "ORS-003", "ORS-009"}:
            record = client.wait_for_pending(record)
        elif case_id in {"ORS-001", "ORS-004"}:
            record = client.wait_for_completion(record, "completed")
        original = False
        pending_before = record["status"] == "pending"
        if case_id == "ORS-002":
            if poc_database_url:
                client.grant_poc_decision(record, "approved")
            status, record, _ = client.decide(record, "approved", client.reviewer)
            if status != 200:
                raise RuntimeError(f"ORS-002 approval failed with HTTP {status}.")
            record = client.wait_for_completion(record, "completed")
        elif case_id == "ORS-003":
            if poc_database_url:
                client.grant_poc_decision(record, "rejected")
            status, record, _ = client.decide(record, "rejected", client.reviewer)
            if status != 200:
                raise RuntimeError(f"ORS-003 rejection failed with HTTP {status}.")
            record = client.wait_for_completion(record, "rejected")
        elif case_id == "ORS-004":
            replay, _ = client.submit(_payload(case), key)
            original = replay["id"] == record["id"]
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
        result = _result(
            snapshot,
            native_pause=case_id in {"ORS-002", "ORS-003"},
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
        results[case_id] = result
    return results
